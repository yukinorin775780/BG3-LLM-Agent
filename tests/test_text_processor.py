"""
单元测试：文本处理器 (core.utils.text_processor)
覆盖 clean_npc_dialogue、format_history_message、parse_llm_json。
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，支持直接运行 python tests/test_text_processor.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.utils.text_processor import (
    clean_npc_dialogue,
    format_history_message,
    parse_llm_json,
)


# -------------------------------------------------------------------------
# clean_npc_dialogue
# -------------------------------------------------------------------------


def test_clean_npc_dialogue():
    speaker = "Shadowheart"

    test_cases = [
        ("[Shadowheart]说： 别碰那个哨子。", "别碰那个哨子。"),
        ("： [Shadowheart]说： 风停了。", "风停了。"),
        ("Shadowheart: 你听见脚步声了吗？", "你听见脚步声了吗？"),
        ("*她叹了口气* 我们走吧。", "*她叹了口气* 我们走吧。"),
        ("我觉得不太对劲。", "我觉得不太对劲。"),
    ]

    for raw_text, expected in test_cases:
        result = clean_npc_dialogue(speaker, raw_text)
        assert result == expected, (
            f"清洗失败！\n原文本: {raw_text}\n期望: {expected}\n实际: {result}"
        )


# -------------------------------------------------------------------------
# format_history_message
# -------------------------------------------------------------------------


def test_format_history_message():
    speaker = "Astarion"
    clean_text = "哎哟，你是在教我做事吗？"
    expected = "[Astarion]: 哎哟，你是在教我做事吗？"

    assert format_history_message(speaker, clean_text) == expected


# -------------------------------------------------------------------------
# parse_llm_json
# -------------------------------------------------------------------------


def test_parse_llm_json_plain():
    """纯 JSON 应正常解析"""
    raw = '{"action_type": "CHAT", "difficulty_class": 0}'
    result = parse_llm_json(raw)
    assert result == {"action_type": "CHAT", "difficulty_class": 0}


def test_parse_llm_json_markdown_wrapped():
    """Markdown 代码块包裹的 JSON 应自动剥离"""
    raw = '```json\n{"action_type": "ATTACK", "dc": 15}\n```'
    result = parse_llm_json(raw)
    assert result == {"action_type": "ATTACK", "dc": 15}


def test_parse_llm_json_markdown_json_prefix():
    """带 json 语言标识的代码块"""
    raw = '```json\n{"key": "value"}\n```'
    result = parse_llm_json(raw)
    assert result == {"key": "value"}


def test_parse_llm_json_invalid_returns_empty(capsys):
    """无效 JSON 应返回空字典并打印警告"""
    result = parse_llm_json("not json at all")
    assert result == {}
    captured = capsys.readouterr()
    assert "系统警告" in captured.out or "无效" in captured.out


def test_parse_llm_json_empty_string():
    """空字符串应返回空字典"""
    result = parse_llm_json("")
    assert result == {}


def test_parse_llm_json_whitespace_only():
    """仅空白字符应返回空字典"""
    result = parse_llm_json("   \n\t  ")
    assert result == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
