"""
Dungeon Master (DM) Module
Analyzes player intent and determines game mechanics (skill checks, DC, etc.)
"""

import os
import json
import re
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
# 获取当前文件所在目录（core/），然后指向 core/prompts/
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


def analyze_intent(user_input: str) -> Dict[str, Any]:
    """
    Analyze player intent and determine game mechanics.
    
    Args:
        user_input: The player's input text
    
    Returns:
        dict: Intent analysis result with keys:
            - action_type: str (DECEPTION, PERSUASION, INTIMIDATION, INSIGHT, ATTACK, NONE)
            - difficulty_class: int (0-30)
            - reason: str (explanation)
    
    Raises:
        RuntimeError: If template loading or LLM call fails
        json.JSONDecodeError: If JSON parsing fails
    """
    # Load and render template
    template = load_dm_template()
    prompt = template.render(user_input=user_input)
    
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
        
        return intent_data
        
    except json.JSONDecodeError as e:
        error_msg = f"Failed to parse JSON from DM response: {e}"
        if response_text:
            error_msg += f"\nResponse text: {response_text[:200]}"
        raise ValueError(error_msg) from e
    except Exception as e:
        raise RuntimeError(f"DM intent analysis failed: {e}")
