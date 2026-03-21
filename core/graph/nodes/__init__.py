"""
LangGraph 节点包：按职责拆分的 Input / DM / Mechanics / Generation。
"""

from core.graph.nodes.dm import advance_speaker_node, dm_node, narration_node
from core.graph.nodes.generation import create_generation_node, generation_node
from core.graph.nodes.input import input_node, world_tick_node
from core.graph.nodes.mechanics import mechanics_node

__all__ = [
    "input_node",
    "world_tick_node",
    "dm_node",
    "advance_speaker_node",
    "narration_node",
    "mechanics_node",
    "create_generation_node",
    "generation_node",
]
