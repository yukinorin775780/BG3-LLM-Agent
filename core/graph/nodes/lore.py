"""
Lore 节点：处理 READ 意图，读取环境中的可阅读文本并按阅读者属性动态解读。
"""

from __future__ import annotations

import copy
import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Optional

import yaml
from openai import OpenAI

from config import settings
from core.utils.text_processor import parse_llm_json

if TYPE_CHECKING:
    from core.graph.graph_state import GameState
else:
    GameState = Dict[str, Any]

logger = logging.getLogger(__name__)
LLM_TIMEOUT_SECONDS = 4.5

_LORE_CACHE: Dict[str, Dict[str, Any]] = {}
DIARY_LORE_IDS = frozenset({"necromancer_diary_1"})
LORE_TIMEOUT_FALLBACK = {
    "narrator_text": "日记上的字迹被血污彻底覆盖...",
    "character_monologue": "（烦躁地啧了一声）完全看不清写了什么，真是浪费时间。",
}


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


def _extract_actor_personality(entity: Dict[str, Any]) -> str:
    attributes = entity.get("attributes")
    if not isinstance(attributes, dict):
        return ""
    personality = attributes.get("personality")
    if not isinstance(personality, dict):
        return ""
    traits = personality.get("traits")
    if not isinstance(traits, list):
        return ""
    normalized_traits = [str(trait).strip() for trait in traits if str(trait).strip()]
    return "；".join(normalized_traits[:3])


def _fallback_read_payload(
    *,
    actor_name: str,
    int_score: int,
    title: str,
    raw_text: str,
) -> Dict[str, str]:
    lowered_text = raw_text.lower()
    diary_like = (
        _normalize_id(title).find("日记") >= 0
        or "gribbo" in lowered_text
        or "铁钥匙" in raw_text
        or "毒气陷阱" in raw_text
    )

    if diary_like:
        if int_score >= 14:
            return {
                "narrator_text": (
                    f"他迅速读懂了《{title}》的布局：Gribbo 与毒气陷阱联动，"
                    "沉重铁钥匙被藏在密室箱子里。"
                ),
                "character_monologue": (
                    "这位死灵法师把机关写在日记里，真是把愚蠢刻进了墓志铭。"
                ),
            }
        if int_score < 10:
            return {
                "narrator_text": (
                    f"他翻着《{title}》只抓到零碎词句：地精、箱子、毒气。"
                ),
                "character_monologue": "字写得像尸斑，我只看懂‘地精’和‘箱子’。"
            }
        return {
            "narrator_text": "他大致看明白了：通道毒气会惊动 Gribbo，钥匙在密室箱子。",
            "character_monologue": "机关不复杂，真正可怕的是写日志的人自信过头。",
        }

    if int_score < 10:
        return {
            "narrator_text": (
                f"他翻阅《{title}》时被术语和污渍打乱思路，只拼出“地精失控”和“走廊毒气”的只言片语。"
            ),
            "character_monologue": "这堆涂鸦看得我头疼。"
        }

    if "米尔寇的叹息" in raw_text and "Myrkul's Breath" in raw_text:
        return {
            "narrator_text": (
                f"他读懂了《{title}》：地精喝药后变聪明并被锁在主控室，走廊布有毒气陷阱，"
                "通行密语是“米尔寇的叹息 (Myrkul's Breath)”。"
            ),
            "character_monologue": "把口令写进日志，这种防御天赋值得被钉在公告墙上。"
        }
    return {
        "narrator_text": f"他读完《{title}》，迅速提炼出其中关于机关与钥匙位置的关键信息。",
        "character_monologue": "线索够用了，剩下就是动手。",
    }


def _build_dynamic_read_prompt(
    *,
    actor_name: str,
    actor_profile: str,
    int_score: int,
    title: str,
    raw_text: str,
) -> str:
    profile_text = actor_profile or "冷静、谨慎、习惯先观察再行动"
    return (
        "你现在是《博德之门3》的地下城主 (DM)。\n"
        f"玩家角色：{actor_name} - {profile_text}。\n"
        f"当前智力值 (INT)：{int_score}。\n"
        f"他正在阅读一本《{title}》。\n\n"
        f"日记事实内容：{raw_text}\n\n"
        "请基于角色的性格和智力值，生成一段他阅读后的内心独白或直接的口头吐槽（100字以内）。\n"
        "- 如果 INT >= 14：他能立刻看透布局，并刻薄地嘲笑陷阱破绽。\n"
        "- 如果 INT < 10：他可能对枯燥文字不耐烦，只提取到“地精”和“箱子”等关键词。\n"
        "- 必须以 JSON 格式返回："
        '{"narrator_text": "系统描述...", "character_monologue": "角色的台词..."}'
    )


def _generate_read_payload(
    *,
    actor_name: str,
    actor_profile: str,
    int_score: int,
    title: str,
    raw_text: str,
) -> Dict[str, str]:
    fallback = _fallback_read_payload(
        actor_name=actor_name,
        int_score=int_score,
        title=title,
        raw_text=raw_text,
    )
    if not settings.API_KEY:
        return fallback

    prompt = _build_dynamic_read_prompt(
        actor_name=actor_name,
        actor_profile=actor_profile,
        int_score=int_score,
        title=title,
        raw_text=raw_text,
    )

    try:
        client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=260,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        parsed = parse_llm_json(content or "")
        narrator_text = str(parsed.get("narrator_text") or "").strip()
        character_monologue = str(parsed.get("character_monologue") or "").strip()
        if narrator_text or character_monologue:
            return {
                "narrator_text": narrator_text or fallback["narrator_text"],
                "character_monologue": character_monologue or fallback["character_monologue"],
            }
    except Exception as exc:
        logger.warning("lore narration generation timed out/failed, static fallback applied: %s", exc)
        return dict(LORE_TIMEOUT_FALLBACK)

    return fallback


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
    actor_profile = _extract_actor_personality(actor)
    read_payload = _generate_read_payload(
        actor_name=actor_name,
        actor_profile=actor_profile,
        int_score=int_score,
        title=title,
        raw_text=raw_text,
    )
    narrator_text = str(read_payload.get("narrator_text") or "").strip()
    character_monologue = str(read_payload.get("character_monologue") or "").strip()
    if not narrator_text:
        narrator_text = _fallback_read_payload(
            actor_name=actor_name,
            int_score=int_score,
            title=title,
            raw_text=raw_text,
        )["narrator_text"]
    base_lore_text = raw_text
    final_output = (
        f"📜 [原文] {base_lore_text}\n\n"
        f"📖 [动作] {narrator_text}\n"
        f"💬 [独白] {character_monologue}"
    )

    return {
        "journal_events": [final_output],
        "entities": entities,
        "environment_objects": environment_objects,
    }
