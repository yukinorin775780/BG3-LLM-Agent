from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Literal


DomainEventType = Literal[
    "actor_spoke",
    "actor_physical_action_requested",
    "actor_memory_update_requested",
    "actor_reflection_requested",
    "actor_belief_updated",
    "world_flag_changed",
]


@dataclass(frozen=True)
class DomainEvent:
    event_id: str
    event_type: DomainEventType
    actor_id: str
    turn_index: int
    visibility: str
    payload: Dict[str, Any]


def event_to_dict(event: DomainEvent) -> Dict[str, Any]:
    return asdict(event)


def event_from_dict(payload: Dict[str, Any]) -> DomainEvent:
    return DomainEvent(
        event_id=str(payload.get("event_id") or ""),
        event_type=str(payload.get("event_type") or "actor_spoke"),  # type: ignore[arg-type]
        actor_id=str(payload.get("actor_id") or ""),
        turn_index=int(payload.get("turn_index") or 0),
        visibility=str(payload.get("visibility") or "party"),
        payload=dict(payload.get("payload") or {}),
    )

