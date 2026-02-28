"""
V2 兼容层：Generation 节点仍依赖 engine 的 generate_dialogue / parse_ai_response。
引擎实现已归档至 archive/v1_legacy/engine.py，此处仅作 re-export。
"""

from archive.v1_legacy.engine import (
    generate_dialogue,
    parse_ai_response,
    update_summary,
)

__all__ = ["generate_dialogue", "parse_ai_response", "update_summary"]
