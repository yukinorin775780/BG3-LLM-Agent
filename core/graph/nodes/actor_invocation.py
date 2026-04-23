from __future__ import annotations

from typing import Any, Dict, List

from core.actors.contracts import ReflectionRequest, actor_decision_to_dict
from core.actors.executor import enqueue_reflection_requests, invoke_actor_runtime
from core.actors.registry import ActorRegistry, get_default_actor_registry
from core.events.models import event_to_dict
from core.events.store import append_pending_events
from core.graph.graph_state import GameState


async def actor_invocation_node(
    state: GameState,
    *,
    actor_registry: ActorRegistry | None = None,
) -> Dict[str, Any]:
    actor_id = str(state.get("current_speaker") or "").strip().lower()
    if not actor_id:
        return {"actor_invocation_mode": "fallback"}

    decision_meta, events, reflections = await invoke_actor_runtime(
        state=dict(state or {}),
        actor_id=actor_id,
        registry=actor_registry or get_default_actor_registry(),
    )
    if decision_meta.get("mode") == "fallback":
        return {"actor_invocation_mode": "fallback"}

    event_dicts = [event_to_dict(event) for event in events]
    pending_events = append_pending_events(dict(state or {}), event_dicts)
    reflection_queue = enqueue_reflection_requests(
        state=dict(state or {}),
        requests=reflections,
    )
    out: Dict[str, Any] = {
        "actor_invocation_mode": "runtime",
        "last_actor_decision": decision_meta,
        "pending_events": pending_events,
        "reflection_queue": reflection_queue,
    }
    return out
