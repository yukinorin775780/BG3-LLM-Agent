"""
文本处理器：清洗大模型生成的冗余 NPC 剧本前缀，以及 LLM JSON 防弹解析。
"""

import json
import re


def parse_llm_json(raw_text: str) -> dict:
    """
    提取并解析 LLM 返回的 JSON，自动剥离 Markdown 代码块包裹。
    支持容错：清洗 `: +2` 等非法正数格式，解析失败时返回空字典以保证调用方不崩溃。
    """
    clean_text = raw_text.strip()
    if clean_text.startswith("```"):
        # 截取第一个和第二个 ``` 之间的内容
        parts = clean_text.split("```")
        if len(parts) >= 3:
            clean_text = parts[1]
        # 如果带有 json 标识，去掉 "json"
        if clean_text.lower().startswith("json"):
            clean_text = clean_text[4:].strip()

    # 正则清洗：去掉键值对中形如 ": +2", ":+2", ":  +5" 的正数前导 + 号（不符合 JSON 规范）
    cleaned_text = re.sub(r"(:\s*)\+(\d+)", r"\1\2", clean_text)

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as e:
        print(f"⚠️ [系统警告] LLM 输出了无效的 JSON 格式: {e}")
        print(f"   清洗后内容: {cleaned_text}")
        return {}  # 兜底返回空字典，保证测试脚本能够继续往下跑


def clean_npc_dialogue(speaker: str, raw_text: str) -> str:
    """
    清洗大模型生成的冗余 NPC 名字前缀。
    例如把 "[Shadowheart]说： 风停了。" 清洗为 "风停了。"
    """
    clean_text = raw_text.strip()

    # 1. 暴力清洗：切掉第一个引号或星号之前的所有废话前缀
    first_quote = clean_text.find('"')
    first_asterisk = clean_text.find('*')
    candidates = [i for i in (first_quote, first_asterisk) if i >= 0]
    if candidates:
        clean_text = clean_text[min(candidates) :].strip()

    # 2. 正则清洗：移除行首出现的类似 "[Shadowheart]说："、"Shadowheart: " 等结构
    clean_text = re.sub(
        r"^[：:\s]*\[?[a-zA-Z\u4e00-\u9fa5]+\]?\s*[：:\s说]+", "", clean_text
    ).strip()

    # 3. 兜底清洗：基于传入的 speaker ID 再次强制正则清洗
    clean_text = re.sub(
        rf"^{re.escape(speaker)}\s*[:：说]\s*", "", clean_text, flags=re.IGNORECASE
    ).strip()

    if not clean_text:
        clean_text = raw_text.strip()
    return clean_text


def format_history_message(speaker: str, clean_text: str) -> str:
    """
    为后台历史记录打上标准的说话人标签，防止大模型产生身份幻觉。
    """
    return f"[{speaker}]: {clean_text}"
