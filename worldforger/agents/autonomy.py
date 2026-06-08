# -*- coding: utf-8 -*-
"""Character autonomy level system.

Three levels control how much freedom a character agent has:
  L1 (advisor):    suggests decisions, human confirms
  L2 (semi-auto):  autonomous, human can override
  L3 (full-auto):  fully autonomous across multiple chapters
"""

from __future__ import annotations

from enum import Enum


class AutonomyLevel(str, Enum):
    ADVISOR = "advisor"        # L1: suggestions only
    SEMI_AUTO = "semi_auto"    # L2: autonomous, overridable
    FULL_AUTO = "full_auto"    # L3: fully independent


# Default level per character role
_DEFAULT_LEVELS: dict[str, AutonomyLevel] = {
    "protagonist_core": AutonomyLevel.SEMI_AUTO,
    "protagonist": AutonomyLevel.SEMI_AUTO,
    "supporting_major": AutonomyLevel.SEMI_AUTO,
    "supporting_minor": AutonomyLevel.ADVISOR,
    "antagonist": AutonomyLevel.SEMI_AUTO,
    "background": AutonomyLevel.ADVISOR,
}


class AutonomyManager:
    """Manage per-character autonomy levels and their effects.

    Higher autonomy = higher temperature, fewer constraints, less oversight.
    """

    @staticmethod
    def default_level(cast_role: str) -> AutonomyLevel:
        """Return default autonomy level for a character cast role."""
        return _DEFAULT_LEVELS.get(cast_role, AutonomyLevel.ADVISOR)

    @staticmethod
    def temperature_for(level: AutonomyLevel, base_temp: float) -> float:
        """Adjust temperature based on autonomy level.

        Higher autonomy → higher temperature → more creative/unpredictable.
        """
        adjustments = {
            AutonomyLevel.ADVISOR: -0.05,    # more predictable
            AutonomyLevel.SEMI_AUTO: 0.0,    # default
            AutonomyLevel.FULL_AUTO: 0.05,   # more creative
        }
        return max(0.1, min(0.9, base_temp + adjustments.get(level, 0.0)))

    @staticmethod
    def constraint_strictness(level: AutonomyLevel) -> float:
        """How strictly macro outline constraints are enforced.

        Returns 0.0 (no enforcement) to 1.0 (strict enforcement).
        """
        return {
            AutonomyLevel.ADVISOR: 0.9,
            AutonomyLevel.SEMI_AUTO: 0.6,
            AutonomyLevel.FULL_AUTO: 0.3,
        }[level]

    @staticmethod
    def max_allowed_severity(level: AutonomyLevel) -> str:
        """Maximum deviation severity that is auto-accepted without intervention.

        ADVISOR:    only "none" is auto-accepted
        SEMI_AUTO:  "light" or below auto-accepted
        FULL_AUTO:  "moderate" or below auto-accepted
        """
        return {
            AutonomyLevel.ADVISOR: "none",
            AutonomyLevel.SEMI_AUTO: "light",
            AutonomyLevel.FULL_AUTO: "moderate",
        }[level]

    @staticmethod
    def should_intervene(
        level: AutonomyLevel,
        beat_deviation_severity: str,
        quality_overall: float,
    ) -> bool:
        """Check if human intervention is needed based on autonomy level."""
        if quality_overall < 25:
            return True

        severity_order = {"none": 0, "light": 1, "moderate": 2, "severe": 3}
        max_allowed_name = AutonomyManager.max_allowed_severity(level)
        max_allowed = severity_order.get(max_allowed_name, 0)
        actual = severity_order.get(beat_deviation_severity, 0)

        return actual > max_allowed

    @staticmethod
    def describe(level: AutonomyLevel) -> str:
        """Human-readable description of this autonomy level."""
        return {
            AutonomyLevel.ADVISOR: "顾问模式：Agent 提供建议，人工确认后执行",
            AutonomyLevel.SEMI_AUTO: "半自主模式：Agent 自主决策，人工可随时推翻",
            AutonomyLevel.FULL_AUTO: "全自主模式：Agent 完全独立运行多章，人工卷末审阅",
        }[level]
