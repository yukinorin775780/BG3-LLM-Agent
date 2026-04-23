from __future__ import annotations

from typing import Any, Dict, List, Tuple

from core.actors import ActorScopedMemoryProvider, build_actor_view
from core.actors.contracts import ReflectionRequest, reflection_request_from_dict, reflection_request_to_dict
from core.actors.registry import ActorRegistry
from core.events.models import DomainEvent, event_to_dict
from core.memory.compat import get_default_memory_service


def _safe_get_runtime(registry: ActorRegistry, actor_id: str):
    if hasattr(registry, "try_get"):
        runtime = registry.try_get(actor_id)
    else:
        runtime = None
    if runtime is not None:
        return runtime
    try:
        return registry.get(actor_id)
    except KeyError:
        return None


async def invoke_actor_runtime(
    *,
    state: Dict[str, Any],
    actor_id: str,
    registry: ActorRegistry,
) -> Tuple[Dict[str, Any], List[DomainEvent], List[ReflectionRequest]]:
    runtime = _safe_get_runtime(registry, actor_id)
    if runtime is None:
        return {"mode": "fallback", "actor_id": actor_id}, [], []

    memory_service = get_default_memory_service()
    actor_view = build_actor_view(
        state,
        actor_id,
        memory_provider=ActorScopedMemoryProvider(memory_service.retriever),
    )
    decision = await runtime.decide(actor_view)
    decision_dict = {
        "mode": "runtime",
        "actor_id": decision.actor_id,
        "kind": decision.kind,
        "spoken_text": decision.spoken_text,
        "thought_summary": decision.thought_summary,
        "physical_action": dict(decision.physical_action or {}) if decision.physical_action else None,
    }
    return decision_dict, list(decision.emitted_events), list(decision.requested_reflections)


async def process_reflection_queue(
    *,
    state: Dict[str, Any],
    registry: ActorRegistry,
    max_items: int = 1,
) -> Dict[str, Any]:
    queue_raw = list(state.get("reflection_queue") or [])
    if not queue_raw:
        return {}

    pending_events = list(state.get("pending_events") or [])
    processed = 0
    remaining: List[Dict[str, Any]] = []
    normalized_requests: List[ReflectionRequest] = []
    for raw_request in queue_raw:
        if isinstance(raw_request, ReflectionRequest):
            normalized_requests.append(raw_request)
            continue
        if processed >= max_items:
            continue
        if not isinstance(raw_request, dict):
            continue
        normalized_requests.append(reflection_request_from_dict(raw_request))

    normalized_requests.sort(
        key=lambda item: -int(item.priority or 0),
    )

    for request in normalized_requests:
        if processed >= max_items:
            remaining.append(reflection_request_to_dict(request))
            continue
        runtime = _safe_get_runtime(registry, request.actor_id)
        if runtime is None:
            continue
        events = await runtime.reflect(request)
        pending_events.extend(event_to_dict(item) for item in events)
        processed += 1

    return {
        "reflection_queue": remaining,
        "pending_events": pending_events,
    }


def enqueue_reflection_requests(
    *,
    state: Dict[str, Any],
    requests: List[ReflectionRequest],
) -> List[Dict[str, Any]]:
    queue = list(state.get("reflection_queue") or [])
    queue.extend(reflection_request_to_dict(item) for item in requests)
    return queue
