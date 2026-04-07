"""
Dungeon Master (DM) Module
Analyzes player intent and determines game mechanics (skill checks, DC, etc.)
"""

import ast
import logging
import operator
import os
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


def analyze_intent(
    user_input: str,
    flags: Optional[Dict[str, Any]] = None,
    time_of_day: str = "晨曦 (Morning)",
    hp: int = 20,
    available_npcs: Optional[List[str]] = None,
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
    # 濒死拦截：HP <= 0 时 NPC 已昏迷，跳过 LLM 判定
    if hp <= 0:
        return {
            "action_type": "CHAT",
            "difficulty_class": 0,
            "reason": "NPC is unconscious/dead.",
            "is_probing_secret": False,
        }

    flags = flags or {}
    available_npcs = available_npcs or list(DEFAULT_AVAILABLE_NPCS)
    npcs_str = ", ".join(f'"{n}"' for n in available_npcs)
    # Load and render template
    template = load_dm_template()
    prompt = template.render(user_input=user_input, flags=flags, time_of_day=time_of_day, available_npcs=npcs_str)
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
