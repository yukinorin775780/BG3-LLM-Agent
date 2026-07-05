from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional
from uuid import uuid4

from core.events.models import DomainEvent, event_to_dict
from core.systems.dice import roll_d20


ToolHandler = Callable[[Mapping[str, Any], Dict[str, Any], str], "ToolExecution"]


@dataclass(frozen=True)
class PlannedToolCall:
    tool_name: str
    arguments: Dict[str, Any]
    display_title: str = ""


@dataclass(frozen=True)
class ToolExecution:
    tool_name: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]
    success: bool
    source: str
    turn_id: str
    display_title: str = ""
    call_id: str = ""
    events: tuple[Dict[str, Any], ...] = ()

    def as_call_record(self) -> Dict[str, Any]:
        return self._as_record("tool_call")

    def as_result_record(self) -> Dict[str, Any]:
        return self._as_record("tool_result")

    def _as_record(self, record_type: str) -> Dict[str, Any]:
        return {
            "type": record_type,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments": copy.deepcopy(self.arguments),
            "result": copy.deepcopy(self.result),
            "success": bool(self.success),
            "source": self.source,
            "turn_id": self.turn_id,
            "display_title": self.display_title or self.tool_name,
        }


@dataclass(frozen=True)
class ToolExecutionBundle:
    executions: tuple[ToolExecution, ...]

    @property
    def tool_calls(self) -> List[Dict[str, Any]]:
        return [execution.as_call_record() for execution in self.executions]

    @property
    def tool_results(self) -> List[Dict[str, Any]]:
        return [execution.as_result_record() for execution in self.executions]

    @property
    def events(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for execution in self.executions:
            out.extend(copy.deepcopy(list(execution.events)))
        return out


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    handler: ToolHandler
    display_title: str


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _inventory_for(state: Mapping[str, Any], actor_id: str) -> Dict[str, Any]:
    normalized_actor = str(actor_id or "").strip().lower()
    if normalized_actor == "player":
        return _safe_dict(state.get("player_inventory"))
    entities = _safe_dict(state.get("entities"))
    actor = _safe_dict(entities.get(normalized_actor))
    return _safe_dict(actor.get("inventory"))


def _memory_known(state: Mapping[str, Any], memory_key: str) -> bool:
    key = str(memory_key or "").strip()
    if not key:
        return False
    flags = _safe_dict(state.get("flags"))
    if _truthy(flags.get(key)):
        return True
    if key == "act3_gribbo_potion_truth_known":
        for alias in (
            "act3_party_knows_gribbo_truth",
            "necromancer_lab_diary_decoded",
            "act3_diary_decoded",
        ):
            if _truthy(flags.get(alias)):
                return True
    runtime_state = _safe_dict(state.get("actor_runtime_state"))
    needle = key.lower()
    for bucket in runtime_state.values():
        notes = _safe_dict(bucket).get("memory_notes")
        if not isinstance(notes, list):
            continue
        if any(needle in str(note or "").lower() for note in notes):
            return True
    return False


def _event_turn_index(turn_id: str) -> int:
    raw = str(turn_id or "").rsplit(":", 1)[-1]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _item_transfer_event(
    *,
    actor_id: str,
    turn_id: str,
    from_actor_id: str,
    to_actor_id: str,
    item_id: str,
    quantity: int,
    reason: str,
) -> Dict[str, Any]:
    return event_to_dict(
        DomainEvent(
            event_id=_new_id("evt"),
            event_type="actor_item_transaction_requested",
            actor_id=actor_id,
            turn_index=_event_turn_index(turn_id),
            visibility="party",
            payload={
                "social_action": {
                    "action_type": "item_transfer",
                    "actor_id": actor_id,
                    "target_actor_id": to_actor_id,
                    "item_id": item_id,
                    "quantity": int(quantity),
                    "accepted": True,
                    "reason": reason,
                },
                "transaction": {
                    "transaction_type": "transfer",
                    "from_entity": from_actor_id,
                    "to_entity": to_actor_id,
                    "item": item_id,
                    "quantity": int(quantity),
                    "accepted": True,
                    "reason": reason,
                },
            },
        )
    )


def _jsonable_roll_result(roll: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(roll)
    result_type = result.get("result_type")
    if hasattr(result_type, "value"):
        result["result_type"] = result_type.value
    else:
        result["result_type"] = str(result_type or "")
    return result


def _query_party_memory(state: Mapping[str, Any], arguments: Dict[str, Any], turn_id: str) -> ToolExecution:
    memory_key = str(arguments.get("memory_key") or "").strip()
    known = _memory_known(state, memory_key)
    result = {"memory_key": memory_key, "known": known}
    return ToolExecution(
        tool_name="query_party_memory",
        arguments={"memory_key": memory_key},
        result=result,
        success=known,
        source="backend_tool_executor",
        turn_id=turn_id,
        display_title="Query Party Memory",
        call_id=_new_id("tool"),
    )


def _check_target_inventory(state: Mapping[str, Any], arguments: Dict[str, Any], turn_id: str) -> ToolExecution:
    target_id = str(arguments.get("target_id") or "").strip().lower()
    item_id = str(arguments.get("item_id") or "").strip().lower()
    inventory = _inventory_for(state, target_id)
    count = int(inventory.get(item_id) or 0) if item_id else 0
    result = {
        "target_id": target_id,
        "item_id": item_id,
        "count": count,
        "has_item": count > 0,
    }
    return ToolExecution(
        tool_name="check_target_inventory",
        arguments={"target_id": target_id, "item_id": item_id},
        result=result,
        success=count > 0,
        source="backend_tool_executor",
        turn_id=turn_id,
        display_title="Check Target Inventory",
        call_id=_new_id("tool"),
    )


def _roll_skill_check(state: Mapping[str, Any], arguments: Dict[str, Any], turn_id: str) -> ToolExecution:
    actor_id = str(arguments.get("actor_id") or "player").strip().lower() or "player"
    skill = str(arguments.get("skill") or "persuasion").strip().lower()
    dc = int(arguments.get("dc") or 10)
    advantage_source = str(arguments.get("advantage_source") or "").strip()
    roll_type = "advantage" if advantage_source else "normal"
    modifier = 2 if actor_id == "player" and skill == "persuasion" else 0
    roll = _jsonable_roll_result(roll_d20(dc=dc, modifier=modifier, roll_type=roll_type))

    flags = _safe_dict(state.get("flags"))
    if skill == "persuasion" and actor_id == "player":
        if _truthy(flags.get("necromancer_lab_force_truth_negotiation_success")):
            roll["is_success"] = True
        if _truthy(flags.get("necromancer_lab_force_truth_negotiation_failure")):
            roll["is_success"] = False
    result = {
        "actor_id": actor_id,
        "skill": skill,
        "dc": dc,
        "modifier": modifier,
        "advantage_source": advantage_source,
        **roll,
    }
    return ToolExecution(
        tool_name="roll_skill_check",
        arguments={
            "actor_id": actor_id,
            "skill": skill,
            "dc": dc,
            "advantage_source": advantage_source or None,
        },
        result=result,
        success=bool(result.get("is_success", False)),
        source="backend_tool_executor",
        turn_id=turn_id,
        display_title="Roll Skill Check",
        call_id=_new_id("tool"),
    )


def _transfer_item(state: Mapping[str, Any], arguments: Dict[str, Any], turn_id: str) -> ToolExecution:
    from_actor_id = str(arguments.get("from_actor_id") or "").strip().lower()
    to_actor_id = str(arguments.get("to_actor_id") or "").strip().lower()
    item_id = str(arguments.get("item_id") or "").strip().lower()
    quantity = max(1, int(arguments.get("quantity") or 1))
    inventory = _inventory_for(state, from_actor_id)
    available = int(inventory.get(item_id) or 0) if item_id else 0
    accepted = bool(from_actor_id and to_actor_id and item_id and available >= quantity)
    events: tuple[Dict[str, Any], ...] = ()
    if accepted:
        events = (
            _item_transfer_event(
                actor_id="player",
                turn_id=turn_id,
                from_actor_id=from_actor_id,
                to_actor_id=to_actor_id,
                item_id=item_id,
                quantity=quantity,
                reason="act4_truth_negotiation_key_surrender",
            ),
        )
    result = {
        "from_actor_id": from_actor_id,
        "to_actor_id": to_actor_id,
        "item_id": item_id,
        "quantity": quantity,
        "available": available,
        "accepted": accepted,
        "event_count": len(events),
    }
    return ToolExecution(
        tool_name="transfer_item",
        arguments={
            "from_actor_id": from_actor_id,
            "to_actor_id": to_actor_id,
            "item_id": item_id,
            "quantity": quantity,
        },
        result=result,
        success=accepted,
        source="backend_tool_executor",
        turn_id=turn_id,
        display_title="Transfer Item",
        call_id=_new_id("tool"),
        events=events,
    )


class ToolRegistry:
    def __init__(self, tools: Iterable[RegisteredTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, tool_name: str) -> RegisteredTool:
        name = str(tool_name or "").strip()
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {tool_name}")
        return self._tools[name]

    def names(self) -> List[str]:
        return sorted(self._tools)


class ToolExecutor:
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self._registry = registry or get_default_tool_registry()

    def execute(self, state: Mapping[str, Any], planned_call: PlannedToolCall, *, turn_id: str) -> ToolExecution:
        tool = self._registry.get(planned_call.tool_name)
        execution = tool.handler(state, dict(planned_call.arguments), turn_id)
        if planned_call.display_title and not execution.display_title:
            return ToolExecution(
                tool_name=execution.tool_name,
                arguments=execution.arguments,
                result=execution.result,
                success=execution.success,
                source=execution.source,
                turn_id=execution.turn_id,
                display_title=planned_call.display_title,
                call_id=execution.call_id,
                events=execution.events,
            )
        return execution


class Act4ToolPlanner:
    def plan_diary_truth_negotiation(self, *, dc: int) -> List[PlannedToolCall]:
        return [
            PlannedToolCall(
                "query_party_memory",
                {"memory_key": "act3_gribbo_potion_truth_known"},
                "Query Party Memory",
            ),
            PlannedToolCall(
                "check_target_inventory",
                {"target_id": "gribbo", "item_id": "heavy_iron_key"},
                "Check Target Inventory",
            ),
            PlannedToolCall(
                "roll_skill_check",
                {
                    "actor_id": "player",
                    "skill": "persuasion",
                    "dc": int(dc),
                    "advantage_source": "diary_truth",
                },
                "Roll Persuasion Check",
            ),
            PlannedToolCall(
                "transfer_item",
                {
                    "from_actor_id": "gribbo",
                    "to_actor_id": "player",
                    "item_id": "heavy_iron_key",
                    "quantity": 1,
                },
                "Transfer Heavy Iron Key",
            ),
        ]


def get_default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            RegisteredTool("query_party_memory", _query_party_memory, "Query Party Memory"),
            RegisteredTool("check_target_inventory", _check_target_inventory, "Check Target Inventory"),
            RegisteredTool("roll_skill_check", _roll_skill_check, "Roll Skill Check"),
            RegisteredTool("transfer_item", _transfer_item, "Transfer Item"),
        ]
    )


def execute_act4_diary_truth_tool_sequence(
    state: Mapping[str, Any],
    *,
    dc: int,
    turn_id: str,
) -> ToolExecutionBundle:
    planner = Act4ToolPlanner()
    executor = ToolExecutor()
    executions: List[ToolExecution] = []
    for planned_call in planner.plan_diary_truth_negotiation(dc=dc):
        if planned_call.tool_name == "transfer_item":
            roll_result = next((item for item in executions if item.tool_name == "roll_skill_check"), None)
            inventory_result = next((item for item in executions if item.tool_name == "check_target_inventory"), None)
            if not roll_result or not roll_result.success or not inventory_result or not inventory_result.success:
                continue
        executions.append(executor.execute(state, planned_call, turn_id=turn_id))
    return ToolExecutionBundle(tuple(executions))


__all__ = [
    "Act4ToolPlanner",
    "PlannedToolCall",
    "ToolExecution",
    "ToolExecutionBundle",
    "ToolExecutor",
    "ToolRegistry",
    "execute_act4_diary_truth_tool_sequence",
    "get_default_tool_registry",
]
