"""
Lore 节点：处理 READ 意图，读取环境中的可阅读文本并按阅读者属性动态解读。
"""

from __future__ import annotations

import copy
import logging
import os
from typing import Any, Dict, Optional

import yaml
from openai import OpenAI

from config import settings
from core.graph.graph_state import GameState
from core.utils.text_processor import parse_llm_json

logger = logging.getLogger(__name__)

_LORE_CACHE: Dict[str, Dict[str, Any]] = {}


def _normalize_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _load_lore_db(force_reload: bool = False) -> Dict[str, Dict[str, Any]]:
    global _LORE_CACHE
    if _LORE_CACHE and not force_reload:
        return _LORE_CACHE
    lore_path = os.path.join(_project_root(), "data", "lore.yaml")
    if not os.path.exists(lore_path):
        _LORE_CACHE = {}
        return _LORE_CACHE
    try:
        with open(lore_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        logger.warning("Failed to load lore yaml: %s", lore_path)
        _LORE_CACHE = {}
        return _LORE_CACHE
    if not isinstance(raw_data, dict):
        _LORE_CACHE = {}
        return _LORE_CACHE
    normalized: Dict[str, Dict[str, Any]] = {}
    for lore_id_raw, lore_data in raw_data.items():
        lore_id = _normalize_id(lore_id_raw)
        if not lore_id or not isinstance(lore_data, dict):
            continue
        normalized[lore_id] = lore_data
    _LORE_CACHE = normalized
    return _LORE_CACHE


def _display_entity_name(entity_id: str, entity: Dict[str, Any]) -> str:
    name = str(entity.get("name") or "").strip()
    if name:
        return name
    if entity_id == "player":
        return "玩家"
    return entity_id.replace("_", " ").strip().title() or "未知角色"


def _resolve_readable_target(
    *,
    environment_objects: Dict[str, Dict[str, Any]],
    target_id: str,
) -> tuple[str, Optional[Dict[str, Any]]]:
    normalized_target = _normalize_id(target_id)
    if not normalized_target:
        return "", None

    if normalized_target in environment_objects:
        target_obj = environment_objects.get(normalized_target)
        if isinstance(target_obj, dict):
            return normalized_target, target_obj

    for object_id, object_data in environment_objects.items():
        if not isinstance(object_data, dict):
            continue
        object_name = _normalize_id(object_data.get("name"))
        normalized_object_id = _normalize_id(object_id)
        if (
            normalized_target in object_name
            or object_name in normalized_target
            or normalized_target in normalized_object_id
            or normalized_object_id in normalized_target
        ):
            return normalized_object_id, object_data
    return "", None


def _extract_actor_int(entity: Dict[str, Any]) -> int:
    ability_scores = entity.get("ability_scores")
    if not isinstance(ability_scores, dict):
        return 10
    for key, value in ability_scores.items():
        if str(key).strip().upper() != "INT":
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10
    return 10


def _fallback_narration(actor_name: str, int_score: int, title: str) -> str:
    if int_score < 10:
        return (
            f"📖 [阅读] {actor_name}翻阅了《{title}》，只勉强看懂“地精失控”和“走廊毒气”的只言片语，"
            "关键密语被术语和污渍搅成一团。"
        )
    return (
        f"📖 [阅读] {actor_name}读懂了《{title}》：一只地精喝下《狐之狡诈》后变得聪明，被锁在主控室；"
        "走廊布有毒气陷阱，通行密语是“米尔寇的叹息 (Myrkul's Breath)”。"
    )


def _generate_read_narration(
    *,
    actor_name: str,
    int_score: int,
    title: str,
    raw_text: str,
) -> str:
    if not settings.API_KEY:
        return _fallback_narration(actor_name, int_score, title)

    prompt = (
        "You are the DM. The player character "
        f"{actor_name} (INT score: {int_score}) is trying to read this document: '{raw_text}'.\n"
        "Rule 1: If INT < 10, they struggle to read. Obscure key details like passwords. Describe their confusion.\n"
        "Rule 2: If INT >= 10, they read it clearly. Summarize the text in a narrative tone.\n"
        "Rule 3: Output strictly in JSON: {'narration': 'Your description of what they read and understand'}."
    )

    try:
        client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=220,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        parsed = parse_llm_json(content or "")
        narration = str(parsed.get("narration") or "").strip()
        if narration:
            return f"📖 [阅读] {narration}"
    except Exception as exc:
        logger.warning("lore narration generation failed, fallback applied: %s", exc)

    return _fallback_narration(actor_name, int_score, title)


def lore_node(state: GameState) -> Dict[str, Any]:
    intent = str(state.get("intent", "CHAT") or "CHAT").strip().upper()
    if intent != "READ":
        return {}

    entities = copy.deepcopy(state.get("entities") or {})
    environment_objects = copy.deepcopy(state.get("environment_objects") or {})
    intent_context = state.get("intent_context") or {}

    actor_id = _normalize_id(intent_context.get("action_actor") or "player")
    target_id = _normalize_id(intent_context.get("action_target"))
    if not actor_id:
        actor_id = "player"

    actor = entities.get(actor_id)
    if not isinstance(actor, dict):
        actor_id = "player"
        actor = entities.get("player")
    if not isinstance(actor, dict):
        return {
            "journal_events": ["❌ [阅读] 无法判定阅读者。"],
            "entities": entities,
            "environment_objects": environment_objects,
        }

    resolved_target_id, target_obj = _resolve_readable_target(
        environment_objects=environment_objects,
        target_id=target_id,
    )
    if not resolved_target_id or not isinstance(target_obj, dict):
        return {
            "journal_events": [f"❌ [阅读] 未找到可阅读目标：{target_id or 'unknown'}。"],
            "entities": entities,
            "environment_objects": environment_objects,
        }

    object_type = _normalize_id(target_obj.get("type"))
    if object_type != "readable":
        return {
            "journal_events": [f"❌ [阅读] 目标 {resolved_target_id} 不是可阅读对象。"],
            "entities": entities,
            "environment_objects": environment_objects,
        }

    lore_id = _normalize_id(target_obj.get("lore_id"))
    lore_db = _load_lore_db()
    lore_entry = lore_db.get(lore_id, {})
    if not isinstance(lore_entry, dict) or not lore_entry:
        return {
            "journal_events": [f"❌ [阅读] 文本条目缺失：{lore_id or 'unknown'}。"],
            "entities": entities,
            "environment_objects": environment_objects,
        }

    title = str(lore_entry.get("title") or target_obj.get("name") or resolved_target_id)
    raw_text = str(lore_entry.get("raw_text") or "").strip()
    if not raw_text:
        return {
            "journal_events": [f"❌ [阅读] 《{title}》没有可读内容。"],
            "entities": entities,
            "environment_objects": environment_objects,
        }

    actor_name = _display_entity_name(actor_id, actor)
    int_score = _extract_actor_int(actor)
    narration = _generate_read_narration(
        actor_name=actor_name,
        int_score=int_score,
        title=title,
        raw_text=raw_text,
    )

    return {
        "journal_events": [narration],
        "entities": entities,
        "environment_objects": environment_objects,
    }

