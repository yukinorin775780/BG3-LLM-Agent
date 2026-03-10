"""
Dungeon Master (DM) Module
Analyzes player intent and determines game mechanics (skill checks, DC, etc.)
"""

import os
import json
import re
from characters.loader import load_character
from typing import Dict, Any
from openai import OpenAI
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from config import settings

# 初始化客户端
if not settings.API_KEY:
    raise RuntimeError(
        "未找到 API Key。请配置 BAILIAN_API_KEY 或 DASHSCOPE_API_KEY 环境变量。"
    )

try:
    client = OpenAI(api_key=settings.API_KEY, base_url=settings.BASE_URL)
except Exception as e:
    raise RuntimeError(f"初始化 AI 客户端失败: {e}")

# 初始化 Jinja2 环境（用于加载 DM prompt 模板）
# 获取当前文件所在目录（core/llm/），然后指向 core/llm/prompts/
_core_dir = os.path.dirname(os.path.abspath(__file__))
_prompts_dir = os.path.join(_core_dir, "prompts")

_jinja_env = Environment(
    loader=FileSystemLoader(_prompts_dir),
    trim_blocks=True,
    lstrip_blocks=True
)


def load_dm_template():
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
    Handles cases where JSON might be wrapped in markdown code blocks.
    
    Args:
        text: Raw text response from LLM
    
    Returns:
        dict: Parsed JSON object
    
    Raises:
        json.JSONDecodeError: If JSON cannot be parsed
    """
    # Remove markdown code blocks if present
    text = text.strip()
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        # Try to find JSON object in the text
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)
    
    # Parse JSON
    return json.loads(text)


def _evaluate_narrative_rules(analysis: dict, flags: dict, target_npc: str = "shadowheart") -> dict:
    """数据驱动的规则引擎：解析 YAML 中的条件表达式，动态覆盖 DM 判定结果"""
    char = load_character(target_npc)
    rules = char.data.get("narrative_rules", [])
    if not rules:
        return analysis

    action_type = analysis.get("action_type", "")
    is_probing_secret = analysis.get("is_probing_secret", False)

    for rule in rules:
        condition_str = rule.get("condition", "False")
        try:
            if eval(
                condition_str,
                {"flags": flags, "action_type": action_type, "is_probing_secret": is_probing_secret},
            ):
                overrides = rule.get("overrides", {})
                for key, value in overrides.items():
                    analysis[key] = value
                print(f"🔮 [Rule Engine] 触发叙事规则覆写: {rule.get('id')}")
        except Exception as e:
            print(f"⚠️ [Rule Engine] 规则 '{rule.get('id')}' 解析失败: {e}")

    return analysis


def analyze_intent(user_input: str, flags: Dict[str, Any] | None = None, time_of_day: str = "晨曦 (Morning)", hp: int = 20, available_npcs: list | None = None) -> Dict[str, Any]:
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
        json.JSONDecodeError: If JSON parsing fails
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
    available_npcs = available_npcs or ["shadowheart", "astarion"]
    npcs_str = ", ".join(f'"{n}"' for n in available_npcs)
    # Load and render template
    template = load_dm_template()
    prompt = template.render(user_input=user_input, flags=flags, time_of_day=time_of_day, available_npcs=npcs_str)
    
    response_text: str | None = None
    
    try:
        # Call LLM
        messages = [{"role": "user", "content": prompt}]
        
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=messages,  # type: ignore
            temperature=0.3,  # Lower temperature for more consistent analysis
            max_tokens=200  # DM analysis should be concise
        )
        
        response_text = completion.choices[0].message.content
        if not response_text:
            raise RuntimeError("LLM returned empty response")
        
        # Parse JSON from response
        intent_data = parse_json_response(response_text)
        
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
        responders = intent_data.get("responders", ["shadowheart"])
        if not isinstance(responders, list) or len(responders) == 0:
            responders = ["shadowheart"]
        responders = [str(r).strip().lower() for r in responders if str(r).strip().lower() in available_npcs]
        if not responders:
            responders = [available_npcs[0]] if available_npcs else ["shadowheart"]
        intent_data["responders"] = responders

        # 剧情标志位变更：安全提取并过滤
        flags_changed = intent_data.get("flags_changed", {})
        if not isinstance(flags_changed, dict):
            flags_changed = {}
        intent_data["flags_changed"] = {str(k): bool(v) for k, v in flags_changed.items()}

        # 好感度变化：安全提取并过滤
        affection_changes = intent_data.get("affection_changes", {})
        if not isinstance(affection_changes, dict):
            affection_changes = {}
        # 只保留合法 NPC 的数值变化
        intent_data["affection_changes"] = {
            str(k).strip().lower(): int(v)
            for k, v in affection_changes.items()
            if str(k).strip().lower() in available_npcs and isinstance(v, (int, float))
        }

        return _evaluate_narrative_rules(intent_data, flags, responders[0] if responders else "shadowheart")
        
    except json.JSONDecodeError as e:
        error_msg = f"Failed to parse JSON from DM response: {e}"
        if response_text:
            error_msg += f"\nResponse text: {response_text[:200]}"
        raise ValueError(error_msg) from e
    except Exception as e:
        raise RuntimeError(f"DM intent analysis failed: {e}")
