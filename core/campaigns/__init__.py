"""Campaign-specific deterministic orchestration helpers."""

from core.campaigns.necromancer_lab import (
    ACT3_CHOICE_REBUKE_ASTARION,
    ACT3_CHOICE_SIDE_WITH_ASTARION,
    ACT4_POST_COMBAT_BANTER,
    detect_lab_act3_choice,
    detect_lab_act4_post_combat_banter,
    detect_lab_intro_awareness,
)

__all__ = [
    "ACT3_CHOICE_REBUKE_ASTARION",
    "ACT3_CHOICE_SIDE_WITH_ASTARION",
    "ACT4_POST_COMBAT_BANTER",
    "detect_lab_act3_choice",
    "detect_lab_act4_post_combat_banter",
    "detect_lab_intro_awareness",
]
