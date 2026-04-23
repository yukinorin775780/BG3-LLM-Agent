from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping

from core.actors.views import PublicEntityView, VisibleMessage

PUBLIC_FLAG_PREFIXES = (
    "world_",
    "quest_",
    "combat_",
    "public_",
)

PUBLIC_ENTITY_FIELDS = {
    "name",
    "position",
    "status",
    "faction",
    "entity_type",
    "hp",
    "max_hp",
}

SELF_ONLY_ENTITY_FIELDS = {
    "inventory",
    "affection",
    "active_buffs",
    "dynamic_states",
    "secret_objective",
}

_SPEAKER_TAG_PATTERN = re.compile(r"^\s*\[([^\]]+)\]\s*[:：]\s*(.*)$", flags=re.DOTALL)


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_role(value: Any) -> str:
    role = _normalize_id(value)
    if role in {"assistant", "ai"}:
        return "assistant"
    if role in {"user", "human"}:
        return "user"
    return "user"


def _extract_message_parts(raw_message: Any) -> tuple[str, str, str]:
    if isinstance(raw_message, Mapping):
        role = _normalize_role(raw_message.get("role"))
        content = str(raw_message.get("content") or "").strip()
        speaker_id = _normalize_id(raw_message.get("name"))
        return role, speaker_id, content

    role = _normalize_role(getattr(raw_message, "type", "user"))
    content = str(getattr(raw_message, "content", "") or "").strip()
    speaker_id = _normalize_id(getattr(raw_message, "name", ""))
    return role, speaker_id, content


def _extract_assistant_speaker_and_content(
    *,
    speaker_id: str,
    content: str,
    actor_id: str,
) -> tuple[str, str]:
    normalized_speaker = _normalize_id(speaker_id)
    normalized_content = str(content or "").strip()

    tagged = _SPEAKER_TAG_PATTERN.match(normalized_content)
    if tagged:
        tagged_speaker = _normalize_id(tagged.group(1))
        tagged_content = str(tagged.group(2) or "").strip()
        if tagged_speaker:
            normalized_speaker = tagged_speaker
        if tagged_content:
            normalized_content = tagged_content

    if not normalized_speaker:
        normalized_speaker = _normalize_id(actor_id) or "assistant"
    return normalized_speaker, normalized_content


def filter_flags_for_actor(flags: Dict[str, Any], actor_id: str) -> Dict[str, bool]:
    _ = actor_id  # Phase 1: actor-specific flags not enforced yet.
    source = _safe_dict(flags)
    visible: Dict[str, bool] = {}
    for key, value in source.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if not normalized_key.startswith(PUBLIC_FLAG_PREFIXES):
            continue
        visible[normalized_key] = bool(value)
    return visible


def filter_environment_objects_for_actor(
    state: Any,
    actor_id: str,
) -> Dict[str, Dict[str, Any]]:
    _ = actor_id  # Phase 1: no actor-specific env filtering yet.
    environment = _safe_dict(_safe_dict(state).get("environment_objects"))
    visible: Dict[str, Dict[str, Any]] = {}

    for object_id, raw_object in environment.items():
        object_data = _safe_dict(raw_object)
        if not object_data:
            continue
        entity_type = _normalize_id(object_data.get("entity_type", object_data.get("type")))
        status = _normalize_id(object_data.get("status"))
        is_hidden = bool(object_data.get("is_hidden", False))

        if entity_type == "trap" and (is_hidden or status == "hidden"):
            continue

        visible[str(object_id)] = dict(object_data)
    return visible


def build_visible_history(messages: List[Any], actor_id: str, limit: int = 12) -> List[VisibleMessage]:
    bounded = list(messages or [])
    if limit > 0:
        bounded = bounded[-limit:]

    normalized: List[VisibleMessage] = []
    for raw_message in bounded:
        role, speaker_id, content = _extract_message_parts(raw_message)
        if not content:
            continue

        if role == "assistant":
            speaker_id, content = _extract_assistant_speaker_and_content(
                speaker_id=speaker_id,
                content=content,
                actor_id=actor_id,
            )
        elif not speaker_id:
            speaker_id = "user"

        normalized.append(
            VisibleMessage(
                role=role,
                speaker_id=speaker_id,
                content=content,
            )
        )
    return normalized


def build_recent_public_events(journal_events: List[str], limit: int = 8) -> List[str]:
    items = [str(item) for item in (journal_events or [])]
    if limit <= 0:
        return []
    return items[-limit:]


def is_party_member_entity(entity_id: str, entity: Dict[str, Any]) -> bool:
    normalized_id = _normalize_id(entity_id)
    if normalized_id in {"player", "shadowheart", "astarion", "laezel"}:
        return True
    faction = _normalize_id(entity.get("faction"))
    return faction not in {"hostile"}


def build_public_entity_view(entity_id: str, entity: Dict[str, Any]) -> PublicEntityView:
    return PublicEntityView(
        entity_id=entity_id,
        name=str(entity.get("name") or entity_id),
        position=str(entity.get("position") or ""),
        status=str(entity.get("status") or ""),
        faction=str(entity.get("faction") or ""),
        entity_type=str(entity.get("entity_type") or entity.get("type") or ""),
        is_party_member=is_party_member_entity(entity_id, entity),
    )

