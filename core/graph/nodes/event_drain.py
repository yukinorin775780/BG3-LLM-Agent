from __future__ import annotations

from typing import Any, Dict, List

from core.actors.contracts import ReflectionRequest, reflection_request_to_dict
from core.actors.executor import process_reflection_queue
from core.actors.registry import ActorRegistry, get_default_actor_registry
from core.events.apply import apply_domain_events
from core.events.models import event_from_dict
from core.events.store import drain_pending_events
from core.graph.graph_state import GameState


def event_drain_node(state: GameState) -> Dict[str, Any]:
    pending = drain_pending_events(dict(state or {}))
    if not pending:
        return {"pending_events": []}

    events = [event_from_dict(item) for item in pending if isinstance(item, dict)]
    patch = apply_domain_events(dict(state or {}), events)
    out: Dict[str, Any] = {
        "pending_events": list(patch.pending_events),
        "actor_runtime_state": patch.actor_runtime_state or {},
        "reflection_queue": list(patch.reflection_queue),
    }
    if patch.entities is not None:
        out["entities"] = patch.entities
    if patch.flags is not None:
        out["flags"] = patch.flags
    if patch.journal_events:
        out["journal_events"] = list(patch.journal_events)
    if patch.messages:
        out["messages"] = list(patch.messages)
    if patch.speaker_responses:
        out["speaker_responses"] = list(patch.speaker_responses)
    if patch.final_response:
        out["final_response"] = patch.final_response
    return out


async def drain_reflection_queue(
    state: GameState,
    *,
    actor_registry: ActorRegistry | None = None,
    max_items: int | None = None,
) -> Dict[str, Any]:
    normalized_state = dict(state or {})
    queue_raw = list(normalized_state.get("reflection_queue") or [])
    normalized_queue: List[Dict[str, Any]] = []
    for item in queue_raw:
        if isinstance(item, ReflectionRequest):
            normalized_queue.append(reflection_request_to_dict(item))
        elif isinstance(item, dict):
            normalized_queue.append(dict(item))
    normalized_state["reflection_queue"] = normalized_queue

    processed = await process_reflection_queue(
        state=normalized_state,
        registry=actor_registry or get_default_actor_registry(),
        max_items=max_items if max_items is not None else max(1, len(normalized_queue)),
    )
    return processed
