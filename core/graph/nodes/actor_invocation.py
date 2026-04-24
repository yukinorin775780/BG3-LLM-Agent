from __future__ import annotations

from typing import Any, Dict, List

from core.actors.executor import (
    FALLBACK_REASON_RUNTIME_FAILED,
    FALLBACK_REASON_RUNTIME_MISSING,
    enqueue_reflection_requests,
    invoke_actor_runtime,
)
from core.actors.registry import ActorRegistry, get_default_actor_registry
from core.eval.telemetry import emit_telemetry
from core.events.models import event_to_dict
from core.events.store import append_pending_events
from core.graph.graph_state import GameState


ACTOR_INVOCATION_MODE_RUNTIME = "runtime"
ACTOR_INVOCATION_MODE_FALLBACK = "fallback"
ACTOR_INVOCATION_MODE_LEGACY = "legacy"
ACTOR_INVOCATION_REASON_RUNTIME_ENABLED = "runtime_enabled"
FALLBACK_REASON_ACTOR_ID_MISSING = "actor_id_missing"
_VALID_FALLBACK_REASONS = frozenset(
    {
        FALLBACK_REASON_RUNTIME_MISSING,
        FALLBACK_REASON_RUNTIME_FAILED,
        FALLBACK_REASON_ACTOR_ID_MISSING,
    }
)


def _normalize_fallback_reason(raw_reason: Any) -> str:
    reason = str(raw_reason or "").strip().lower()
    if reason in _VALID_FALLBACK_REASONS:
        return reason
    return FALLBACK_REASON_RUNTIME_FAILED


def _fallback_response(actor_id: str, reason: Any) -> Dict[str, Any]:
    normalized_reason = _normalize_fallback_reason(reason)
    normalized_actor_id = str(actor_id or "").strip().lower() or "unknown"
    emit_telemetry(
        "actor_runtime_decision",
        actor_id=normalized_actor_id,
        mode="fallback",
        reason=normalized_reason,
        decision_kind="fallback",
        emitted_event_count=0,
        reflection_request_count=0,
        duration_ms=0,
    )
    return {
        "actor_invocation_mode": ACTOR_INVOCATION_MODE_FALLBACK,
        "actor_invocation_reason": normalized_reason,
    }


async def actor_invocation_node(
    state: GameState,
    *,
    actor_registry: ActorRegistry | None = None,
) -> Dict[str, Any]:
    actor_id = str(state.get("current_speaker") or "").strip().lower()
    if not actor_id:
        return _fallback_response(actor_id, FALLBACK_REASON_ACTOR_ID_MISSING)

    decision_meta, events, reflections = await invoke_actor_runtime(
        state=dict(state or {}),
        actor_id=actor_id,
        registry=actor_registry or get_default_actor_registry(),
    )
    if decision_meta.get("mode") == "fallback":
        return _fallback_response(actor_id, decision_meta.get("reason"))

    event_dicts = [event_to_dict(event) for event in events]
    pending_events = append_pending_events(dict(state or {}), event_dicts)
    reflection_queue = enqueue_reflection_requests(
        state=dict(state or {}),
        requests=reflections,
    )
    out: Dict[str, Any] = {
        "actor_invocation_mode": ACTOR_INVOCATION_MODE_RUNTIME,
        "actor_invocation_reason": ACTOR_INVOCATION_REASON_RUNTIME_ENABLED,
        "last_actor_decision": decision_meta,
        "pending_events": pending_events,
        "reflection_queue": reflection_queue,
    }
    if reflections:
        emit_telemetry(
            "reflection_enqueued",
            actor_id=actor_id,
            count=len(reflections),
            queue_size=len(reflection_queue),
        )
    return out
