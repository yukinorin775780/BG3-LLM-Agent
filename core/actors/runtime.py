from __future__ import annotations

import time
from typing import Any, Dict, Tuple
from uuid import uuid4

from core.actors.contracts import ActorDecision, ReflectionRequest
from core.actors.views import ActorView
from core.campaigns import (
    ACT3_CHOICE_REBUKE_ASTARION,
    ACT3_CHOICE_SIDE_WITH_ASTARION,
)
from core.eval.telemetry import emit_telemetry
from core.events.models import DomainEvent
from core.systems.inventory import get_registry


def _new_event_id() -> str:
    return f"evt_{uuid4().hex}"


_GIFT_OFFER_MARKERS = ("给你", "送你", "拿着", "收下", "take this", "give you", "gift")
_ITEM_USE_MARKERS = ("喝", "服用", "使用", "drink", "use")
_MERCY_CHOICE_MARKERS = ("仁慈", "放过", "饶", "不杀", "mercy", "spare")
_CIVILIAN_PRIORITY_MARKERS = ("救平民", "先救", "救人", "save civilians", "save the civilian")
_ACT3_SIDE_MARKERS = (
    "阿斯代伦说得对",
    "一起嘲笑",
    "同意阿斯代伦",
    "side with astarion",
    "mock gribbo",
)
_ACT3_REBUKE_MARKERS = (
    "阿斯代伦，闭嘴",
    "阿斯代伦闭嘴",
    "别拱火",
    "rebuke astarion",
    "shut up astarion",
)


def _contains_any(text: str, markers: Tuple[str, ...]) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in markers)


def _detect_party_choice_context(text: str) -> str:
    if _contains_any(text, _MERCY_CHOICE_MARKERS):
        return "mercy_choice"
    if _contains_any(text, _CIVILIAN_PRIORITY_MARKERS):
        return "civilian_priority_choice"
    return ""


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_necromancer_lab_act3(actor_view: ActorView) -> bool:
    active_target = _normalize_id(actor_view.intent_context.get("action_target"))
    if active_target != "gribbo":
        return False
    visible_flags = actor_view.visible_flags if isinstance(actor_view.visible_flags, dict) else {}
    if bool(visible_flags.get("world_necromancer_lab_intro_entered")):
        return True
    location_text = str(actor_view.current_location or "")
    return ("necromancer_lab" in location_text.lower()) or ("实验室" in location_text)


def _detect_act3_choice_context(actor_view: ActorView) -> str:
    if not _is_necromancer_lab_act3(actor_view):
        return ""

    explicit_choice = _normalize_id(
        actor_view.intent_context.get("act3_choice")
        or actor_view.intent_context.get("choice")
    )
    if explicit_choice in {ACT3_CHOICE_SIDE_WITH_ASTARION, ACT3_CHOICE_REBUKE_ASTARION}:
        return explicit_choice

    user_input = str(actor_view.user_input or "")
    normalized_input = user_input.strip().lower()
    if not normalized_input:
        return ""
    if any(marker in user_input or marker in normalized_input for marker in _ACT3_SIDE_MARKERS):
        return ACT3_CHOICE_SIDE_WITH_ASTARION
    if any(marker in user_input or marker in normalized_input for marker in _ACT3_REBUKE_MARKERS):
        return ACT3_CHOICE_REBUKE_ASTARION
    return ""


def _detect_act4_post_combat_context(actor_view: ActorView) -> bool:
    explicit = bool(actor_view.intent_context.get("act4_post_combat_banter"))
    if not explicit:
        return False
    visible_flags = actor_view.visible_flags if isinstance(actor_view.visible_flags, dict) else {}
    if not bool(visible_flags.get("world_necromancer_lab_gribbo_defeated")):
        return False
    location_text = str(actor_view.current_location or "").strip().lower()
    return "necromancer" in location_text or "实验室" in str(actor_view.current_location or "")


def _key_guidance_context(actor_view: ActorView) -> Dict[str, Any]:
    payload = actor_view.intent_context.get("key_guidance_context")
    if not isinstance(payload, dict):
        return {}
    if str(payload.get("topic") or "").strip().lower() != "lab_key":
        return {}
    return dict(payload)


def _build_key_guidance_metadata(*, actor_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
    if not context:
        return {}
    return {
        "type": "companion_guidance",
        "topic": "lab_key",
        "has_key": bool(context.get("has_lab_key", False)),
        "door_id": str(context.get("door_id") or "door_b_to_d"),
        "actor_id": actor_id,
    }


def _diary_negotiation_context(actor_view: ActorView) -> Dict[str, Any]:
    payload = actor_view.intent_context.get("diary_negotiation_context")
    if not isinstance(payload, dict):
        return {}
    if str(payload.get("topic") or "").strip().lower() != "gribbo_elixir_truth":
        return {}
    if not bool(payload.get("decoded_diary", False)):
        return {}
    return dict(payload)


def _build_diary_pressure_events(
    *,
    actor_id: str,
    turn_index: int,
    context: Dict[str, Any],
) -> Tuple[DomainEvent, ...]:
    if actor_id != "shadowheart" or not context:
        return ()
    try:
        current_patience = int(context.get("patience_current", 10) or 10)
    except (TypeError, ValueError):
        current_patience = 10
    next_patience = max(0, current_patience - 1)
    return (
        DomainEvent(
            event_id=_new_event_id(),
            event_type="actor_negotiation_outcome_requested",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={
                "target_actor_id": "gribbo",
                "patience_set": next_patience,
                "fear_delta": 1,
                "paranoia_delta": 1,
                "force_hostile": False,
                "trigger_combat": False,
                "reason": "diary_evidence_pressure",
            },
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="world_flag_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={"key": "necromancer_lab_gribbo_truth_pressure", "value": True},
        ),
    )


def _build_act3_memory_note(choice_context: str) -> str:
    if choice_context == ACT3_CHOICE_SIDE_WITH_ASTARION:
        return "玩家与我一起嘲笑了 Gribbo，这种默契让我满意。"
    if choice_context == ACT3_CHOICE_REBUKE_ASTARION:
        return "玩家当众训斥了我，我会记住这笔账。"
    return ""


def _build_act3_runtime_events(
    *,
    actor_id: str,
    turn_index: int,
    choice_context: str,
) -> Tuple[DomainEvent, ...]:
    if choice_context not in {ACT3_CHOICE_SIDE_WITH_ASTARION, ACT3_CHOICE_REBUKE_ASTARION}:
        return ()

    sided_with_astarion = choice_context == ACT3_CHOICE_SIDE_WITH_ASTARION
    affection_delta = 2 if sided_with_astarion else -3
    fear_delta = 2 if sided_with_astarion else 3
    paranoia_delta = 1 if sided_with_astarion else 4
    outcome_reason = "mockery_escalation" if sided_with_astarion else "paranoia_meltdown"

    events = [
        DomainEvent(
            event_id=_new_event_id(),
            event_type="actor_affection_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={
                "target_actor_id": actor_id,
                "delta": affection_delta,
                "reason": f"act3_{choice_context}",
            },
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="actor_memory_update_requested",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="private",
            payload={
                "scope": "actor_private",
                "memory_type": "relationship",
                "text": _build_act3_memory_note(choice_context),
            },
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="actor_negotiation_outcome_requested",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={
                "target_actor_id": "gribbo",
                "patience_set": 0,
                "fear_delta": fear_delta,
                "paranoia_delta": paranoia_delta,
                "force_hostile": True,
                "trigger_combat": True,
                "reason": outcome_reason,
            },
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="world_flag_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={"key": "necromancer_lab_gribbo_negotiation_started", "value": True},
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="world_flag_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={"key": "necromancer_lab_astarion_mocked_gribbo", "value": True},
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="world_flag_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={"key": "necromancer_lab_player_sided_with_astarion", "value": sided_with_astarion},
        ),
        DomainEvent(
            event_id=_new_event_id(),
            event_type="world_flag_changed",
            actor_id=actor_id,
            turn_index=turn_index,
            visibility="party",
            payload={"key": "necromancer_lab_gribbo_combat_triggered", "value": True},
        ),
    ]
    return tuple(events)


def _build_choice_memory_note(*, actor_id: str, choice_context: str) -> str:
    if choice_context == "mercy_choice":
        if actor_id == "laezel":
            return "laezel 记录小队抉择：反对仁慈放敌。"
        if actor_id == "shadowheart":
            return "shadowheart 记录小队抉择：谨慎支持仁慈。"
        if actor_id == "astarion":
            return "astarion 记录小队抉择：对仁慈选择保持讥讽。"
        return f"{actor_id} 记录小队抉择：对仁慈选择有明确态度。"
    if choice_context == "civilian_priority_choice":
        if actor_id == "shadowheart":
            return "shadowheart 记录小队抉择：优先救援平民。"
        if actor_id == "astarion":
            return "astarion 记录小队抉择：对英雄式优先级保持怀疑。"
        if actor_id == "laezel":
            return "laezel 记录小队抉择：反对延后追击敌人。"
        return f"{actor_id} 记录小队抉择：对救援优先级表达立场。"
    return ""


def _build_act4_memory_note(*, actor_id: str, sided_with_astarion: bool) -> str:
    if actor_id == "shadowheart":
        return "Gribbo 倒下后，我仍能感到死灵残渣。拿到钥匙不代表安全。"
    if actor_id == "laezel":
        return "目标已完成：拿钥匙、开门、撤离。拖延毫无意义。"
    if sided_with_astarion:
        return "玩家在 Gribbo 事件里与我同调。拿到钥匙后应立刻离开。"
    return "玩家曾当众压我一头，但钥匙到手后我依旧选择推进撤离。"


def _resolve_item_id_from_text(text: str) -> str:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return ""

    direct_map = {
        "治疗药水": "healing_potion",
        "healing_potion": "healing_potion",
        "potion": "healing_potion",
        "莎尔圣徽": "holy_symbol_of_shar",
        "holy symbol of shar": "holy_symbol_of_shar",
        "神器": "mysterious_artifact",
        "artifact": "mysterious_artifact",
    }
    for key, item_id in direct_map.items():
        if key in normalized:
            return item_id

    registry = get_registry()
    for token in normalized.replace("，", " ").replace(",", " ").split():
        resolved = registry.resolve_item_id(token)
        if resolved:
            return str(resolved).strip().lower()
    return ""


def _gift_reject_reason(actor_id: str, item_id: str) -> str:
    # V1.3 baseline policy: Astarion rejects unsolicited gifts to validate reject/return protocol.
    if actor_id == "astarion" and item_id in {"healing_potion", "holy_symbol_of_shar", "mysterious_artifact"}:
        return "unwanted_gift"
    return ""


def _build_social_action(actor_view: ActorView) -> Dict[str, Any]:
    user_input = str(actor_view.user_input or "").strip()
    if not user_input:
        return {}
    item_id = _resolve_item_id_from_text(user_input)
    if not item_id:
        return {}

    actor_id = str(actor_view.actor_id or "").strip().lower()
    if _contains_any(user_input, _GIFT_OFFER_MARKERS):
        reject_reason = _gift_reject_reason(actor_id, item_id)
        if reject_reason:
            return {
                "action_type": "gift_reject",
                "actor_id": actor_id,
                "target_actor_id": "player",
                "item_id": item_id,
                "quantity": 1,
                "accepted": False,
                "reason": reject_reason,
            }
        return {
            "action_type": "gift_accept",
            "actor_id": actor_id,
            "target_actor_id": "player",
            "item_id": item_id,
            "quantity": 1,
            "accepted": True,
            "reason": "accepted_gift",
        }

    if _contains_any(user_input, _ITEM_USE_MARKERS):
        return {
            "action_type": "item_use",
            "actor_id": actor_id,
            "target_actor_id": actor_id,
            "item_id": item_id,
            "quantity": 1,
            "accepted": True,
            "reason": "item_use_requested",
        }
    return {}


def _social_action_to_transaction_payload(action: Dict[str, Any]) -> Dict[str, Any]:
    action_type = str(action.get("action_type") or "").strip().lower()
    accepted = bool(action.get("accepted", False))
    actor_id = str(action.get("actor_id") or "").strip().lower()
    item_id = str(action.get("item_id") or "").strip().lower()
    quantity = max(1, int(action.get("quantity", 1) or 1))
    reason = str(action.get("reason") or "").strip()

    if action_type == "gift_accept":
        return {
            "transaction_type": "transfer",
            "from_entity": "player",
            "to_entity": actor_id,
            "item": item_id,
            "quantity": quantity,
            "accepted": accepted,
            "reason": reason,
        }
    if action_type == "gift_reject":
        return {
            "transaction_type": "no_op",
            "from_entity": "player",
            "to_entity": actor_id,
            "item": item_id,
            "quantity": quantity,
            "accepted": accepted,
            "reason": reason,
        }
    if action_type == "item_use":
        return {
            "transaction_type": "consume",
            "from_entity": actor_id,
            "to_entity": "consumed",
            "item": item_id,
            "quantity": quantity,
            "accepted": accepted,
            "reason": reason,
        }
    return {
        "transaction_type": "no_op",
        "from_entity": actor_id,
        "to_entity": actor_id,
        "item": item_id,
        "quantity": quantity,
        "accepted": False,
        "reason": "unsupported_social_action",
    }


class TemplateActorRuntime:
    """
    Phase 3 V1 runtime:
    - actor-scoped input
    - deterministic decision output
    - emits events only (no direct world mutation)
    """

    def __init__(self, actor_id: str) -> None:
        self.actor_id = str(actor_id or "").strip().lower()

    async def decide(self, actor_view: ActorView) -> ActorDecision:
        started_at = time.perf_counter()
        user_input = str(actor_view.user_input or "").strip()
        if not user_input:
            decision = ActorDecision(actor_id=self.actor_id, kind="silent")
            duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
            emit_telemetry(
                "llm_call",
                component="actor_runtime",
                actor_id=self.actor_id,
                provider="template_runtime",
                model="template_actor_runtime",
                success=True,
                duration_ms=duration_ms,
                token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            )
            emit_telemetry(
                "actor_runtime_decision",
                actor_id=self.actor_id,
                decision_kind=decision.kind,
                emitted_event_count=0,
                reflection_request_count=0,
                duration_ms=duration_ms,
            )
            return decision

        social_action = _build_social_action(actor_view)
        choice_context = _detect_party_choice_context(user_input)
        act3_choice_context = _detect_act3_choice_context(actor_view)
        act4_post_combat_context = _detect_act4_post_combat_context(actor_view)
        key_guidance_context = _key_guidance_context(actor_view)
        diary_negotiation_context = _diary_negotiation_context(actor_view)
        if diary_negotiation_context:
            social_action = {}
        spoken_text = self._compose_reply(
            actor_view,
            social_action=social_action,
            choice_context=choice_context,
            act3_choice_context=act3_choice_context,
            act4_post_combat_context=act4_post_combat_context,
            key_guidance_context=key_guidance_context,
            diary_negotiation_context=diary_negotiation_context,
        )
        spoke_payload: Dict[str, Any] = {"text": spoken_text}
        guidance_metadata = _build_key_guidance_metadata(
            actor_id=self.actor_id,
            context=key_guidance_context,
        )
        if guidance_metadata:
            spoke_payload["guidance"] = guidance_metadata
        events = [
            DomainEvent(
                event_id=_new_event_id(),
                event_type="actor_spoke",
                actor_id=self.actor_id,
                turn_index=int(actor_view.turn_count or 0),
                visibility="party",
                payload=spoke_payload,
            )
        ]
        if social_action:
            transaction_payload = _social_action_to_transaction_payload(social_action)
            event_payload: Dict[str, Any] = {
                "social_action": social_action,
                "transaction": transaction_payload,
            }
            if (
                str(transaction_payload.get("transaction_type") or "") == "consume"
                and str(transaction_payload.get("item") or "") == "healing_potion"
            ):
                event_payload["hp_changes"] = [{"target": self.actor_id, "amount": 5}]
            events.append(
                DomainEvent(
                    event_id=_new_event_id(),
                    event_type="actor_item_transaction_requested",
                    actor_id=self.actor_id,
                    turn_index=int(actor_view.turn_count or 0),
                    visibility="party",
                    payload=event_payload,
                )
            )
            memory_text = (
                f"{self.actor_id} 记录社交物品互动："
                f"{social_action.get('action_type')} {social_action.get('item_id')} ({social_action.get('reason')})"
            )
            events.append(
                DomainEvent(
                    event_id=_new_event_id(),
                    event_type="actor_memory_update_requested",
                    actor_id=self.actor_id,
                    turn_index=int(actor_view.turn_count or 0),
                    visibility="private",
                    payload={"text": memory_text, "memory_type": "social_item_interaction"},
                )
            )
        elif choice_context:
            choice_memory_note = _build_choice_memory_note(
                actor_id=self.actor_id,
                choice_context=choice_context,
            )
            if choice_memory_note:
                events.append(
                    DomainEvent(
                        event_id=_new_event_id(),
                        event_type="actor_memory_update_requested",
                        actor_id=self.actor_id,
                        turn_index=int(actor_view.turn_count or 0),
                        visibility="private",
                    payload={"text": choice_memory_note, "memory_type": "party_choice_reaction"},
                    )
                )
        if self.actor_id == "astarion" and act3_choice_context:
            events.extend(
                _build_act3_runtime_events(
                    actor_id=self.actor_id,
                    turn_index=int(actor_view.turn_count or 0),
                    choice_context=act3_choice_context,
                )
            )
        if act4_post_combat_context and self.actor_id in {"astarion", "shadowheart", "laezel"}:
            sided_with_astarion = bool(actor_view.intent_context.get("player_sided_with_astarion", False))
            memory_note = _build_act4_memory_note(
                actor_id=self.actor_id,
                sided_with_astarion=sided_with_astarion,
            )
            events.append(
                DomainEvent(
                    event_id=_new_event_id(),
                    event_type="actor_memory_update_requested",
                    actor_id=self.actor_id,
                    turn_index=int(actor_view.turn_count or 0),
                    visibility="private",
                    payload={
                        "scope": "actor_private",
                        "memory_type": "post_combat_reflection",
                        "text": memory_note,
                    },
                )
            )
        if diary_negotiation_context:
            events.extend(
                _build_diary_pressure_events(
                    actor_id=self.actor_id,
                    turn_index=int(actor_view.turn_count or 0),
                    context=diary_negotiation_context,
                )
            )
        requested_reflections: Tuple[ReflectionRequest, ...] = ()
        if any(token in user_input for token in ("秘密", "真相", "信仰", "过去")):
            requested_reflections = (
                ReflectionRequest(
                    actor_id=self.actor_id,
                    reason="sensitive_topic_triggered",
                    priority=2,
                    source_turn=int(actor_view.turn_count or 0),
                    payload={"user_input": user_input},
                ),
            )
        decision = ActorDecision(
            actor_id=self.actor_id,
            kind="speak",
            spoken_text=spoken_text,
            thought_summary="runtime_decision",
            emitted_events=tuple(events),
            requested_reflections=requested_reflections,
        )
        duration_ms = max(0, int(round((time.perf_counter() - started_at) * 1000)))
        emit_telemetry(
            "llm_call",
            component="actor_runtime",
            actor_id=self.actor_id,
            provider="template_runtime",
            model="template_actor_runtime",
            success=True,
            duration_ms=duration_ms,
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        )
        emit_telemetry(
            "actor_runtime_decision",
            actor_id=self.actor_id,
            decision_kind=decision.kind,
            emitted_event_count=len(decision.emitted_events),
            reflection_request_count=len(decision.requested_reflections),
            duration_ms=duration_ms,
        )
        return decision

    async def reflect(self, request: ReflectionRequest) -> Tuple[DomainEvent, ...]:
        belief_text = f"{self.actor_id} 在反思中记录：{request.reason}"
        return (
            DomainEvent(
                event_id=_new_event_id(),
                event_type="actor_belief_updated",
                actor_id=self.actor_id,
                turn_index=int(request.source_turn or 0),
                visibility="director_only",
                payload={
                    "reason": request.reason,
                    "belief": belief_text,
                    "priority": int(request.priority or 0),
                },
            ),
            DomainEvent(
                event_id=_new_event_id(),
                event_type="actor_memory_update_requested",
                actor_id=self.actor_id,
                turn_index=int(request.source_turn or 0),
                visibility="private",
                payload={"text": belief_text},
            ),
        )

    def _compose_reply(
        self,
        actor_view: ActorView,
        *,
        social_action: Dict[str, Any],
        choice_context: str = "",
        act3_choice_context: str = "",
        act4_post_combat_context: bool = False,
        key_guidance_context: Dict[str, Any] | None = None,
        diary_negotiation_context: Dict[str, Any] | None = None,
    ) -> str:
        action_type = str(social_action.get("action_type") or "").strip().lower()
        if action_type == "gift_accept":
            if self.actor_id == "shadowheart":
                return "……我收下了。别声张。"
            return "我收下了。继续。"
        if action_type == "gift_reject":
            if self.actor_id == "astarion":
                return "把你的施舍收回去。我不需要。"
            return "不需要，把它拿回去。"
        if action_type == "item_use":
            return "我用了它。继续。"

        if choice_context == "mercy_choice":
            if self.actor_id == "laezel":
                return "软弱。放过敌人只会让战斗回到我们身上。"
            if self.actor_id == "shadowheart":
                return "仁慈不是罪，但你要承担后果。"
            if self.actor_id == "astarion":
                return "真意外，你今天居然选了仁慈。"
            return "你选择了仁慈，希望代价值得。"
        if choice_context == "civilian_priority_choice":
            if self.actor_id == "shadowheart":
                return "先救平民是对的，至少今晚我能睡得着。"
            if self.actor_id == "astarion":
                return "你要当英雄？那就别拖慢我们。"
            if self.actor_id == "laezel":
                return "先救弱者会耗掉追击窗口。"
            return "先救平民可以，但别失去节奏。"

        if key_guidance_context:
            has_lab_key = bool(key_guidance_context.get("has_lab_key", False))
            if has_lab_key:
                if self.actor_id == "astarion":
                    return "lab_key 都到手了，亲爱的，去打开 door_b_to_d 那扇实验室门。"
                if self.actor_id == "shadowheart":
                    return "钥匙在你手上，打开实验室门，别等这里的力量再聚拢。"
                if self.actor_id == "laezel":
                    return "钥匙已取得。打开 door_b_to_d 实验室门，面对里面的东西。"
                return "钥匙已经在手上，打开实验室门。"

            if self.actor_id == "astarion":
                return "lab_key 不在你包里，亲爱的。先找书房和暗门，翻 study_chest；或者让我撬锁。"
            if self.actor_id == "shadowheart":
                return "没有钥匙就别硬说能开。死灵痕迹指向书房和 necromancer_diary，先读日记再搜箱子。"
            if self.actor_id == "laezel":
                return "没有 lab_key。钥匙、撬锁、破门，选一个。别浪费时间。"
            return "没有钥匙。先找书房线索，或尝试撬锁。"

        if diary_negotiation_context:
            if self.actor_id == "shadowheart":
                return "日记说得够清楚了：这是死灵污染，不是天赋。继续逼问很危险，但能动摇他。"
            if self.actor_id == "astarion":
                return "原来那瓶聪明药把你变得这么可悲。钥匙呢，Gribbo？"
            if self.actor_id == "laezel":
                return "这是弱点。逼问他，把钥匙逼出来。"
            return "日记里的证据可以压住他的谎话。"

        if self.actor_id == "astarion":
            if act3_choice_context == ACT3_CHOICE_SIDE_WITH_ASTARION:
                return "看见了吗，Gribbo？连玩家都觉得你可笑。"
            if act3_choice_context == ACT3_CHOICE_REBUKE_ASTARION:
                return "当众让我闭嘴？行，我记下了。"

        if act4_post_combat_context:
            if self.actor_id == "shadowheart":
                return "死灵气息淡了些，但别松懈。我们先离开这里。"
            if self.actor_id == "laezel":
                return "废话够了。开门，继续前进。"
            if self.actor_id == "astarion":
                sided_with_astarion = bool(actor_view.intent_context.get("player_sided_with_astarion", False))
                if sided_with_astarion:
                    return "至少你这次没拖后腿。钥匙到手，走人。"
                return "别误会，我只是想离开这鬼地方。"

        user_input = str(actor_view.user_input or "").strip()
        if "谢谢" in user_input:
            return "收起你的客气，把眼睛放在前方。"
        if "开门" in user_input:
            return "门会开，但别指望我替你收拾烂摊子。"
        if "攻击" in user_input or "战斗" in user_input:
            return "我在看着。你最好别失手。"
        return "我听见了。继续。"
