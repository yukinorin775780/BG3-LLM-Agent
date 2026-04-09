"""
Dungeon Master (DM) Module
Analyzes player intent and determines game mechanics (skill checks, DC, etc.)
"""

import ast
import logging
import operator
import os
import re
from typing import Any, Dict, List, Mapping, Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateNotFound
from openai import OpenAI

from characters.loader import load_character
from config import settings
from core.utils.text_processor import parse_llm_json

logger = logging.getLogger(__name__)

DEFAULT_AVAILABLE_NPCS = ["shadowheart", "astarion"]
DEFAULT_TARGET_NPC = DEFAULT_AVAILABLE_NPCS[0]
_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda left, right: left in right,
    ast.NotIn: lambda left, right: left not in right,
}
_client: Optional[OpenAI] = None
PLAYER_TARGET_ALIASES = frozenset({"我", "自己", "玩家", "me", "player"})
MOVE_KEYWORDS = ("移动到", "走向", "走到", "靠近", "接近", "过去", "move", "approach", "去")
RETURN_TO_PLAYER_KEYWORDS = (
    "过来",
    "来我这",
    "来这里",
    "到我这",
    "我身边",
    "我旁边",
    "我这里",
    "我这边",
    "comehere",
    "cometome",
)
ATTACK_KEYWORDS = ("攻击", "砍", "砍死", "杀", "干掉", "宰了", "attack", "hit", "strike")
LOOT_KEYWORDS = ("搜刮", "搜尸", "摸尸", "拾取", "loot")
ENTITY_ALIAS_MAP = {
    "shadowheart": ("shadowheart", "影心"),
    "astarion": ("astarion", "阿斯代伦", "阿斯"),
    "laezel": ("laezel", "莱埃泽尔", "莱泽尔", "莱埃", "莱泽"),
    "player": tuple(PLAYER_TARGET_ALIASES),
    "camp_fire": ("camp_fire", "campfire", "篝火", "营火", "火堆", "fire"),
    "iron_chest": ("iron_chest", "铁箱子", "箱子", "宝箱", "chest"),
}


# 初始化 Jinja2 环境（用于加载 DM prompt 模板）
# 获取当前文件所在目录（core/llm/），然后指向 core/llm/prompts/
_core_dir = os.path.dirname(os.path.abspath(__file__))
_prompts_dir = os.path.join(_core_dir, "prompts")

_jinja_env = Environment(
    loader=FileSystemLoader(_prompts_dir),
    trim_blocks=True,
    lstrip_blocks=True
)


class RuleEvaluationError(ValueError):
    """Raised when a narrative rule contains unsupported syntax."""


def _create_openai_client() -> OpenAI:
    """Create the OpenAI client only when DM analysis actually needs it."""
    if not settings.API_KEY:
        raise RuntimeError(
            "未找到 API Key。请配置 BAILIAN_API_KEY 或 DASHSCOPE_API_KEY 环境变量。"
        )

    try:
        return OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
    except Exception as exc:
        raise RuntimeError(f"初始化 AI 客户端失败: {exc}")


def _get_openai_client() -> OpenAI:
    """Return a cached OpenAI client with lazy initialization."""
    global _client
    if _client is None:
        _client = _create_openai_client()
    return _client


def load_dm_template() -> Template:
    """
    Load the DM prompt template.
    
    Returns:
        jinja2.Template: The loaded DM prompt template
    
    Raises:
        TemplateNotFound: If the template file doesn't exist
    """
    try:
        template = _jinja_env.get_template("dm.j2")
        return template
    except TemplateNotFound:
        raise TemplateNotFound(
            f"DM template not found: {os.path.join(_prompts_dir, 'dm.j2')}"
        )


def parse_json_response(text: str) -> Dict[str, Any]:
    """
    Parse JSON from LLM response text.
    委托给 parse_llm_json，自动剥离 Markdown 代码块，解析失败时返回空字典。
    """
    return parse_llm_json(text)


def _evaluate_rule_node(node: ast.AST, context: Mapping[str, Any]) -> Any:
    """Safely evaluate a restricted AST used by narrative rule conditions."""
    if isinstance(node, ast.BoolOp):
        values = [_evaluate_rule_node(value, context) for value in node.values]
        if isinstance(node.op, ast.And):
            return all(values)
        if isinstance(node.op, ast.Or):
            return any(values)
        raise RuleEvaluationError(f"Unsupported boolean operator: {type(node.op).__name__}")

    if isinstance(node, ast.Compare):
        left = _evaluate_rule_node(node.left, context)
        for op_node, comparator in zip(node.ops, node.comparators):
            right = _evaluate_rule_node(comparator, context)
            comparator_fn = _COMPARISON_OPERATORS.get(type(op_node))
            if comparator_fn is None:
                raise RuleEvaluationError(
                    f"Unsupported comparison operator: {type(op_node).__name__}"
                )
            if not comparator_fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_evaluate_rule_node(node.operand, context))

    if isinstance(node, ast.Name):
        if node.id in context:
            return context[node.id]
        raise RuleEvaluationError(f"Unknown variable: {node.id}")

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.List):
        return [_evaluate_rule_node(element, context) for element in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_rule_node(element, context) for element in node.elts)

    if isinstance(node, ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id == "flags":
            flags = context.get("flags", {})
            if isinstance(flags, Mapping):
                return flags.get(node.attr)
            raise RuleEvaluationError("flags must be a mapping for attribute access")
        raise RuleEvaluationError(f"Unsupported attribute access: {ast.dump(node)}")

    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "flags"
            and node.func.attr == "get"
        ):
            flags = context.get("flags", {})
            if not isinstance(flags, Mapping):
                raise RuleEvaluationError("flags must be a mapping for get() access")
            args = [_evaluate_rule_node(argument, context) for argument in node.args]
            if len(args) == 1:
                return flags.get(args[0])
            if len(args) == 2:
                return flags.get(args[0], args[1])
            raise RuleEvaluationError("flags.get only supports one or two arguments")
        raise RuleEvaluationError(f"Unsupported function call: {ast.dump(node)}")

    raise RuleEvaluationError(f"Unsupported AST node: {type(node).__name__}")


def _evaluate_rule_condition(condition: str, context: Mapping[str, Any]) -> bool:
    """Safely evaluate a narrative rule condition against the provided context."""
    normalized_condition = str(condition or "").strip()
    if not normalized_condition:
        return False

    try:
        expression = ast.parse(normalized_condition, mode="eval")
        return bool(_evaluate_rule_node(expression.body, context))
    except (SyntaxError, RuleEvaluationError, TypeError, ValueError) as exc:
        logger.warning("Unsupported rule expression '%s': %s", normalized_condition, exc)
        return False


def _evaluate_narrative_rules(
    analysis: Dict[str, Any],
    flags: Dict[str, Any],
    target_npc: str = DEFAULT_TARGET_NPC,
) -> Dict[str, Any]:
    """数据驱动的规则引擎：安全解析条件表达式，动态覆盖 DM 判定结果。"""
    char = load_character(target_npc)
    rules = char.data.get("narrative_rules", [])
    if not rules:
        return analysis

    context: Dict[str, Any] = dict(analysis)
    context["flags"] = flags

    for rule in rules:
        condition_str = rule.get("condition", "False")
        if _evaluate_rule_condition(str(condition_str), context):
            overrides = rule.get("overrides", {})
            if not isinstance(overrides, dict):
                continue
            analysis.update(overrides)
            context.update(overrides)
            logger.info("触发叙事规则覆写: %s", rule.get("id"))

    return analysis


def _normalize_reference_text(value: str) -> str:
    return re.sub(r"[\s_\-，,。.!！？:：]+", "", str(value or "").strip().lower())


def _candidate_aliases(entity_id: str) -> List[str]:
    normalized_id = str(entity_id or "").strip().lower()
    aliases = list(ENTITY_ALIAS_MAP.get(normalized_id, ()))
    aliases.append(normalized_id)
    return [alias for alias in aliases if str(alias).strip()]


def _extract_command_actor(user_input: str, available_npcs: List[str]) -> Optional[str]:
    normalized_text = _normalize_reference_text(user_input)
    if not normalized_text:
        return None

    normalized_npcs = [str(npc).strip().lower() for npc in available_npcs if str(npc).strip()]
    for actor_id in normalized_npcs:
        if actor_id == "player":
            continue
        for alias in _candidate_aliases(actor_id):
            normalized_alias = _normalize_reference_text(alias)
            if not normalized_alias:
                continue
            alias_position = normalized_text.find(normalized_alias)
            if alias_position < 0:
                continue
            if (
                normalized_text.startswith(f"让{normalized_alias}")
                or normalized_text.startswith(f"叫{normalized_alias}")
                or normalized_text.startswith(f"请{normalized_alias}")
                or normalized_text.startswith(normalized_alias)
            ):
                return actor_id

    return None


def _extract_target_segment(user_input: str, actor_id: str) -> str:
    return _extract_target_segment_for_keywords(user_input, actor_id, MOVE_KEYWORDS)


def _extract_target_segment_for_keywords(user_input: str, actor_id: str, keywords: tuple[str, ...]) -> str:
    normalized_text = _normalize_reference_text(user_input)
    normalized_actor_aliases = [_normalize_reference_text(alias) for alias in _candidate_aliases(actor_id)]
    if actor_id != "player" and any(keyword in normalized_text for keyword in RETURN_TO_PLAYER_KEYWORDS):
        return "player"

    for keyword in keywords:
        normalized_keyword = _normalize_reference_text(keyword)
        keyword_position = normalized_text.find(normalized_keyword)
        if keyword_position < 0:
            continue
        segment = normalized_text[keyword_position + len(normalized_keyword):]
        for alias in normalized_actor_aliases:
            if alias and segment.startswith(alias):
                segment = segment[len(alias):]
        return segment
    return ""


def _resolve_target_id_from_segment(
    *,
    available_targets: List[str],
    actor_id: str,
    normalized_segment: str,
) -> str:
    normalized_targets = [str(target).strip().lower() for target in available_targets if str(target).strip()]
    if normalized_segment in PLAYER_TARGET_ALIASES:
        return "player"

    for candidate in normalized_targets:
        if candidate == actor_id:
            continue
        candidate_id = _normalize_reference_text(candidate)
        if candidate_id and (
            candidate_id in normalized_segment or normalized_segment in candidate_id
        ):
            return candidate

    for candidate in normalized_targets:
        if candidate == actor_id:
            continue
        normalized_aliases = [_normalize_reference_text(alias) for alias in _candidate_aliases(candidate)]
        if any(alias and (alias in normalized_segment or normalized_segment in alias) for alias in normalized_aliases):
            return candidate

    if any(alias in normalized_segment for alias in ("地精", "哥布林", "goblin")):
        for candidate in normalized_targets:
            if candidate != actor_id and candidate.startswith("goblin"):
                return candidate

    if any(alias in normalized_segment for alias in ("宝箱", "箱子", "铁箱子", "chest")):
        if "iron_chest" in normalized_targets and actor_id != "iron_chest":
            return "iron_chest"

    if any(alias in normalized_segment for alias in ("篝火", "营火", "火堆", "campfire", "fire")):
        if "camp_fire" in normalized_targets and actor_id != "camp_fire":
            return "camp_fire"

    return ""


def _resolve_move_target_id(
    *,
    user_input: str,
    available_targets: List[str],
    actor_id: str,
) -> str:
    target_segment = _extract_target_segment(user_input, actor_id)
    normalized_segment = _normalize_reference_text(target_segment)
    return _resolve_target_id_from_segment(
        available_targets=available_targets,
        actor_id=actor_id,
        normalized_segment=normalized_segment,
    )


def _resolve_action_target_id(
    *,
    user_input: str,
    available_targets: List[str],
    actor_id: str,
    keywords: tuple[str, ...],
) -> str:
    target_segment = _extract_target_segment_for_keywords(user_input, actor_id, keywords)
    normalized_segment = _normalize_reference_text(target_segment)
    return _resolve_target_id_from_segment(
        available_targets=available_targets,
        actor_id=actor_id,
        normalized_segment=normalized_segment,
    )


def _build_responders(actor_id: str, available_npcs: List[str]) -> List[str]:
    normalized_npcs = [str(npc).strip().lower() for npc in available_npcs if str(npc).strip()]
    responders = [npc for npc in normalized_npcs if npc != actor_id]
    if actor_id != "player" and actor_id in normalized_npcs:
        responders = [actor_id] + [npc for npc in responders if npc != actor_id]
    if not responders:
        responders = normalized_npcs[:1] or [DEFAULT_TARGET_NPC]
    return responders[:1]


def _detect_loot_intent(
    user_input: str,
    available_npcs: List[str],
    available_targets: List[str],
) -> Optional[Dict[str, Any]]:
    """
    轻量规则：前端点击搜刮时的固定文案优先直达 LOOT，避免依赖 LLM 分类。
    """
    text = str(user_input or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if not any(keyword in lowered or keyword in text for keyword in LOOT_KEYWORDS):
        return None

    normalized_npcs = [str(npc).strip().lower() for npc in available_npcs if str(npc).strip()]
    actor_id = _extract_command_actor(text, normalized_npcs) or "player"
    normalized_targets = [str(target).strip().lower() for target in available_targets if str(target).strip()]
    target_id = ""
    for candidate in normalized_targets:
        if candidate and candidate in lowered:
            target_id = candidate
            break

    if not target_id:
        target_id = _resolve_action_target_id(
            user_input=text,
            available_targets=available_targets,
            actor_id=actor_id,
            keywords=LOOT_KEYWORDS,
        )

    if not target_id:
        match = re.search(r"(?:loot|搜刮|搜尸|摸尸|拾取)\s+([a-zA-Z0-9_]+)", text, flags=re.IGNORECASE)
        if match:
            target_id = match.group(1).strip().lower()

    if not target_id:
        return None

    return {
        "action_type": "LOOT",
        "difficulty_class": 0,
        "reason": "A character is attempting to loot a target.",
        "is_probing_secret": False,
        "responders": _build_responders(actor_id, available_npcs),
        "affection_changes": {},
        "flags_changed": {},
        "item_transfers": [],
        "hp_changes": [],
        "action_actor": actor_id,
        "action_target": target_id,
    }


def _detect_attack_intent(
    user_input: str,
    available_npcs: List[str],
    available_targets: List[str],
) -> Optional[Dict[str, Any]]:
    text = str(user_input or "").strip()
    if not text:
        return None

    lowered = text.lower()
    if not any(keyword in lowered or keyword in text for keyword in ATTACK_KEYWORDS):
        return None

    normalized_npcs = [str(npc).strip().lower() for npc in available_npcs if str(npc).strip()]
    actor_id = _extract_command_actor(text, normalized_npcs) or "player"
    target_id = _resolve_action_target_id(
        user_input=text,
        available_targets=available_targets,
        actor_id=actor_id,
        keywords=ATTACK_KEYWORDS,
    )
    if not target_id:
        return None

    return {
        "action_type": "ATTACK",
        "difficulty_class": 0,
        "reason": "A character is attacking a target.",
        "is_probing_secret": False,
        "responders": _build_responders(actor_id, available_npcs),
        "affection_changes": {},
        "flags_changed": {},
        "item_transfers": [],
        "hp_changes": [],
        "action_actor": actor_id,
        "action_target": target_id,
    }


def _detect_move_intent(
    user_input: str,
    available_npcs: List[str],
    available_targets: List[str],
) -> Optional[Dict[str, Any]]:
    """
    轻量规则：移动/靠近类输入优先直达 MOVE，避免依赖 LLM 输出稳定性。
    """
    text = str(user_input or "").strip()
    if not text:
        return None

    lowered = text.lower()
    move_keywords = (*MOVE_KEYWORDS, *RETURN_TO_PLAYER_KEYWORDS)
    if not any(keyword in lowered or keyword in text for keyword in move_keywords):
        return None

    normalized_npcs = [str(npc).strip().lower() for npc in available_npcs if str(npc).strip()]
    actor_id = _extract_command_actor(text, normalized_npcs) or "player"
    target_id = _resolve_move_target_id(
        user_input=text,
        available_targets=available_targets,
        actor_id=actor_id,
    )

    if not target_id:
        return None

    return {
        "action_type": "MOVE",
        "difficulty_class": 0,
        "reason": "A character is moving toward a target.",
        "is_probing_secret": False,
        "responders": _build_responders(actor_id, available_npcs),
        "affection_changes": {},
        "flags_changed": {},
        "item_transfers": [],
        "hp_changes": [],
        "action_actor": actor_id,
        "action_target": target_id,
    }


def analyze_intent(
    user_input: str,
    flags: Optional[Dict[str, Any]] = None,
    time_of_day: str = "晨曦 (Morning)",
    hp: int = 20,
    available_npcs: Optional[List[str]] = None,
    available_targets: Optional[List[str]] = None,
    item_lore: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze player intent and determine game mechanics.
    
    Args:
        user_input: The player's input text
        flags: Current world-state flags for context-aware intent analysis and rule engine
        hp: NPC current HP for濒死拦截

    Returns:
        dict: Intent analysis result with keys:
            - action_type: str (DECEPTION, PERSUASION, INTIMIDATION, INSIGHT, ATTACK, NONE)
            - difficulty_class: int (0-30)
            - reason: str (explanation)
    
    Raises:
        RuntimeError: If template loading or LLM call fails
    """
    available_npcs = available_npcs or list(DEFAULT_AVAILABLE_NPCS)
    available_targets = available_targets or list(available_npcs)
    move_result = _detect_move_intent(user_input, available_npcs, available_targets)
    if move_result is not None:
        return move_result
    attack_result = _detect_attack_intent(user_input, available_npcs, available_targets)
    if attack_result is not None:
        return attack_result
    shortcut_result = _detect_loot_intent(user_input, available_npcs, available_targets)
    if shortcut_result is not None:
        return shortcut_result

    # 濒死拦截：HP <= 0 时 NPC 已昏迷，跳过 LLM 判定
    if hp <= 0:
        return {
            "action_type": "CHAT",
            "difficulty_class": 0,
            "reason": "NPC is unconscious/dead.",
            "is_probing_secret": False,
        }

    flags = flags or {}
    npcs_str = ", ".join(f'"{n}"' for n in available_npcs)
    targets_str = ", ".join(f'"{t}"' for t in available_targets)
    # Load and render template
    template = load_dm_template()
    prompt = template.render(
        user_input=user_input,
        flags=flags,
        time_of_day=time_of_day,
        available_npcs=npcs_str,
        available_targets=targets_str,
    )
    if item_lore:
        prompt += "\n\n" + item_lore
    
    response_text: Optional[str] = None
    
    try:
        # Call LLM
        messages = [{"role": "user", "content": prompt}]
        client = _get_openai_client()
        
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=messages,  # type: ignore
            temperature=0.3,  # Lower temperature for more consistent analysis
            max_tokens=200  # DM analysis should be concise
        )
        
        response_text = completion.choices[0].message.content
        if not response_text:
            raise RuntimeError("LLM returned empty response")
        
        # Parse JSON from response（防弹解析：失败时返回空字典）
        intent_data = parse_json_response(response_text)

        # 解析失败时兜底，防止游戏崩溃
        if not intent_data:
            return {
                "action_type": "CHAT",
                "difficulty_class": 0,
                "reason": "JSON parse failed, fallback to CHAT.",
                "is_probing_secret": False,
                "responders": available_npcs[:1] or [DEFAULT_TARGET_NPC],
                "affection_changes": {},
                "flags_changed": {},
                "item_transfers": [],
                "hp_changes": [],
            }

        # Validate required fields
        required_fields = ['action_type', 'difficulty_class', 'reason']
        for field in required_fields:
            if field not in intent_data:
                raise ValueError(f"Missing required field in intent analysis: {field}")
        
        # Ensure difficulty_class is an integer
        intent_data['difficulty_class'] = int(intent_data['difficulty_class'])
        
        # Ensure action_type is uppercase
        intent_data['action_type'] = str(intent_data['action_type']).upper()
        intent_data["action_actor"] = str(intent_data.get("action_actor", "player")).strip().lower() or "player"
        intent_data["action_target"] = str(intent_data.get("action_target", "")).strip().lower()
        heuristic_actor = _extract_command_actor(user_input, available_npcs)
        if heuristic_actor and intent_data["action_type"] != "CHAT" and intent_data["action_actor"] == "player":
            intent_data["action_actor"] = heuristic_actor
        if intent_data["action_type"] in {"MOVE", "APPROACH"}:
            heuristic_target = _resolve_move_target_id(
                user_input=user_input,
                available_targets=available_targets,
                actor_id=intent_data["action_actor"],
            )
            if heuristic_target and not intent_data["action_target"]:
                intent_data["action_target"] = heuristic_target
            if intent_data["action_target"] in PLAYER_TARGET_ALIASES:
                intent_data["action_target"] = "player"

        # Topic flag: is_probing_secret (optional, default False)
        intent_data['is_probing_secret'] = bool(intent_data.get('is_probing_secret', False))

        # 多人发言队列：responders（DM 决定的发言顺序）
        responders = intent_data.get("responders", [DEFAULT_TARGET_NPC])
        if not isinstance(responders, list) or len(responders) == 0:
            responders = [DEFAULT_TARGET_NPC]
        responders = [str(r).strip().lower() for r in responders if str(r).strip().lower() in available_npcs]
        if not responders:
            responders = [available_npcs[0]] if available_npcs else [DEFAULT_TARGET_NPC]
        intent_data["responders"] = responders

        # 剧情标志位变更：安全提取并过滤
        flags_changed = intent_data.get("flags_changed", {})
        if not isinstance(flags_changed, dict):
            flags_changed = {}
        intent_data["flags_changed"] = {str(k): bool(v) for k, v in flags_changed.items()}

        # 物理物品转移：安全提取并过滤
        item_transfers_raw = intent_data.get("item_transfers", [])
        if not isinstance(item_transfers_raw, list):
            item_transfers_raw = []
        intent_data["item_transfers"] = [
            {"from": str(t.get("from", "player")), "to": str(t.get("to", "")), "item_id": str(t.get("item_id", "")), "count": int(t.get("count", 1))}
            for t in item_transfers_raw if isinstance(t, dict) and t.get("to") and t.get("item_id")
        ]

        # 生命值变动：安全提取并过滤
        hp_changes_raw = intent_data.get("hp_changes", [])
        if not isinstance(hp_changes_raw, list):
            hp_changes_raw = []
        intent_data["hp_changes"] = [
            {"target": str(t.get("target", "")), "amount": int(t.get("amount", 0))}
            for t in hp_changes_raw if isinstance(t, dict) and t.get("target") is not None and isinstance(t.get("amount"), (int, float))
        ]

        # 好感度变化：安全提取并过滤
        # 【为 Dynamic Persona 让路】Shadowheart 已实装独立的自我反思状态机，DM 不得覆盖其好感度。
        # 即使大模型违反 prompt 输出了 shadowheart 的 affection_changes，代码层也必须拦截。
        affection_changes = intent_data.get("affection_changes", {})
        if not isinstance(affection_changes, dict):
            affection_changes = {}
        filtered = {}
        for k, v in affection_changes.items():
            npc_id = str(k).strip().lower()
            raw_key = str(k).strip()
            if npc_id not in available_npcs or not isinstance(v, (int, float)):
                continue
            # 黑名单：shadowheart / 影心 由 Dynamic Persona 管理，DM 不得覆盖
            if npc_id == "shadowheart" or "影心" in raw_key:
                logger.info(
                    "Ignored affection change for Shadowheart (Dynamic Persona owns this)."
                )
                continue
            filtered[npc_id] = int(v)
        intent_data["affection_changes"] = filtered

        return _evaluate_narrative_rules(
            intent_data,
            flags,
            responders[0] if responders else DEFAULT_TARGET_NPC,
        )

    except Exception as e:
        raise RuntimeError(f"DM intent analysis failed: {e}")
