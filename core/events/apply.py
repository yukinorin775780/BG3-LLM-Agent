from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from langchain_core.messages import AIMessage

from core.actors.contracts import StatePatch
from core.events.models import DomainEvent
from core.utils.text_processor import format_history_message


def _apply_actor_spoke(
    *,
    event: DomainEvent,
    messages: List[Any],
    speaker_responses: List[Tuple[str, str]],
    journal_events: List[str],
) -> str:
    text = str(event.payload.get("text") or "").strip()
    if not text:
        return ""
    speaker_id = str(event.actor_id or "").strip().lower()
    messages.append(AIMessage(content=format_history_message(speaker_id, text), name=speaker_id))
    speaker_responses.append((speaker_id, text))
    journal_events.append(f"💬 [台词] {speaker_id}: \"{text}\"")
    return text


def _apply_world_flag_changed(
    *,
    event: DomainEvent,
    flags: Dict[str, Any],
) -> None:
    key = str(event.payload.get("key") or event.payload.get("flag") or "").strip()
    if not key:
        return
    flags[key] = bool(event.payload.get("value", True))


def apply_domain_events(state: Dict[str, Any], events: List[DomainEvent]) -> StatePatch:
    entities = copy.deepcopy(state.get("entities") or {})
    flags = dict(state.get("flags") or {})
    messages: List[Any] = []
    speaker_responses: List[Tuple[str, str]] = []
    journal_events: List[str] = []
    reflection_queue = list(state.get("reflection_queue") or [])
    actor_runtime_state = copy.deepcopy(state.get("actor_runtime_state") or {})
    final_response = ""

    for event in events:
        if event.event_type == "actor_spoke":
            latest = _apply_actor_spoke(
                event=event,
                messages=messages,
                speaker_responses=speaker_responses,
                journal_events=journal_events,
            )
            if latest:
                final_response = latest
            continue

        if event.event_type == "world_flag_changed":
            _apply_world_flag_changed(event=event, flags=flags)
            journal_events.append("📜 [系统] 世界标志已更新。")
            continue

        if event.event_type == "actor_reflection_requested":
            reflection_queue.append(
                {
                    "actor_id": event.actor_id,
                    "reason": str(event.payload.get("reason") or "unspecified"),
                    "priority": int(event.payload.get("priority") or 0),
                    "source_turn": int(event.turn_index or 0),
                    "payload": dict(event.payload),
                }
            )
            journal_events.append(f"🧠 [后台] {event.actor_id} 安排了一次反思。")
            continue

        if event.event_type == "actor_belief_updated":
            runtime_state = dict(actor_runtime_state.get(event.actor_id) or {})
            beliefs = list(runtime_state.get("beliefs") or [])
            belief_text = str(event.payload.get("belief") or "").strip()
            if belief_text:
                beliefs.append(belief_text)
                runtime_state["beliefs"] = beliefs[-20:]
            actor_runtime_state[event.actor_id] = runtime_state
            journal_events.append(f"🧠 [认知] {event.actor_id} 的内部信念发生了变化。")
            continue

        if event.event_type == "actor_memory_update_requested":
            journal_events.append(f"🧠 [记忆] {event.actor_id} 记录了一条私有记忆。")
            continue

        if event.event_type == "actor_physical_action_requested":
            journal_events.append(f"⚙️ [行动请求] {event.actor_id} 请求了物理动作结算。")
            continue

    return StatePatch(
        entities=entities,
        flags=flags,
        journal_events=tuple(journal_events),
        messages=tuple(messages),
        speaker_responses=tuple(speaker_responses),
        reflection_queue=tuple(reflection_queue),
        actor_runtime_state=actor_runtime_state,
        pending_events=tuple(),
        final_response=final_response,
    )
