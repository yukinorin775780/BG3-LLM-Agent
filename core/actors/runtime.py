from __future__ import annotations

from typing import Tuple
from uuid import uuid4

from core.actors.contracts import ActorDecision, ReflectionRequest
from core.actors.views import ActorView
from core.events.models import DomainEvent


def _new_event_id() -> str:
    return f"evt_{uuid4().hex}"


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
        user_input = str(actor_view.user_input or "").strip()
        if not user_input:
            return ActorDecision(actor_id=self.actor_id, kind="silent")

        # Minimal deterministic phrasing to keep runtime predictable in tests.
        spoken_text = self._compose_reply(actor_view)
        events = (
            DomainEvent(
                event_id=_new_event_id(),
                event_type="actor_spoke",
                actor_id=self.actor_id,
                turn_index=int(actor_view.turn_count or 0),
                visibility="party",
                payload={"text": spoken_text},
            ),
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
        return ActorDecision(
            actor_id=self.actor_id,
            kind="speak",
            spoken_text=spoken_text,
            thought_summary="runtime_decision",
            emitted_events=events,
            requested_reflections=requested_reflections,
        )

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

    def _compose_reply(self, actor_view: ActorView) -> str:
        user_input = str(actor_view.user_input or "").strip()
        if "谢谢" in user_input:
            return "收起你的客气，把眼睛放在前方。"
        if "开门" in user_input:
            return "门会开，但别指望我替你收拾烂摊子。"
        if "攻击" in user_input or "战斗" in user_input:
            return "我在看着。你最好别失手。"
        return "我听见了。继续。"

