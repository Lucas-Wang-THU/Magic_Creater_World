# -*- coding: utf-8 -*-
"""Narrative quality auto-evaluation for emergent storytelling.

Scores generated chapters along five dimensions:
  pacing, character_arc, dialog_quality, world_consistency, reader_engagement.
"""

from __future__ import annotations

from worldforger.agents.types import AgentSimResult


class QualityEvaluator:
    """Score narrative quality across multiple dimensions.

    Scores are 0-100. No LLM calls — heuristic based on simulation data.
    """

    DIMENSIONS = [
        "pacing",           # scene rhythm, peak/valley alternation
        "character_arc",    # character change across chapters
        "dialog",           # conflict + emotion + info in conversations
        "consistency",      # cross-chapter state continuity
        "engagement",       # overall reader interest potential
    ]

    @staticmethod
    def evaluate(
        sim_result: AgentSimResult,
        prev_quality: dict | None = None,
        continuity_issues: int = 0,
    ) -> dict:
        """Return a quality report with per-dimension scores and overall."""
        scores = {}

        # Pacing: decision density + variety
        scores["pacing"] = QualityEvaluator._score_pacing(sim_result)

        # Character arc: emotional shifts + relationship changes
        scores["character_arc"] = QualityEvaluator._score_character_arc(sim_result)

        # Dialog: delegate to DialogQuality
        from worldforger.agents.dialog_quality import DialogQuality
        dq = DialogQuality.assess(sim_result)
        scores["dialog"] = dq["overall"]

        # Consistency: inverse of continuity issues
        scores["consistency"] = max(0, 100 - continuity_issues * 15)

        # Engagement: weighted combination
        scores["engagement"] = round(
            scores["pacing"] * 0.15 +
            scores["character_arc"] * 0.30 +
            scores["dialog"] * 0.25 +
            scores["consistency"] * 0.30,
            1,
        )

        overall = round(sum(scores.values()) / len(scores), 1)

        # Trend analysis
        trend = None
        if prev_quality and "overall" in prev_quality:
            delta = overall - prev_quality["overall"]
            if delta > 10:
                trend = "improving"
            elif delta < -10:
                trend = "declining"
            else:
                trend = "stable"

        suggestions = QualityEvaluator._generate_suggestions(scores, trend)

        return {
            "scores": scores,
            "overall": overall,
            "trend": trend,
            "suggestions": suggestions,
            "grade": QualityEvaluator._grade(overall),
        }

    @staticmethod
    def _score_pacing(sim_result: AgentSimResult) -> int:
        decisions = sim_result.decision_sequence
        if not decisions:
            return 20
        score = 50
        # Variety: different characters deciding
        chars = set(d.character_id for d in decisions)
        score += min(len(chars) * 10, 20)
        # Action density
        active = [d for d in decisions if d.intended_action and len(d.intended_action) > 5]
        score += min(len(active) * 3, 15)
        # Speech variety
        speeches = [d for d in decisions if d.intended_speech]
        score += min(len(speeches) * 3, 15)
        return min(score, 100)

    @staticmethod
    def _score_character_arc(sim_result: AgentSimResult) -> int:
        decisions = sim_result.decision_sequence
        if not decisions:
            return 20
        score = 30
        # Emotional shifts
        shifts = [d for d in decisions if d.emotional_shift]
        score += min(len(shifts) * 10, 30)
        # Relationship changes
        rel_changes = [d for d in decisions if d.relationship_changes]
        score += min(len(rel_changes) * 10, 20)
        # New goals formed
        new_goals = [d for d in decisions if d.new_short_term_goal]
        score += min(len(new_goals) * 10, 20)
        return min(score, 100)

    @staticmethod
    def _grade(overall: float) -> str:
        if overall >= 75:
            return "A"
        elif overall >= 60:
            return "B"
        elif overall >= 45:
            return "C"
        elif overall >= 30:
            return "D"
        return "F"

    @staticmethod
    def _generate_suggestions(scores: dict, trend: str | None) -> list[str]:
        suggestions: list[str] = []
        thresholds = {"pacing": 40, "character_arc": 35, "dialog": 35, "consistency": 50, "engagement": 40}
        labels = {
            "pacing": "节奏偏弱：增加主动行动和对话密度",
            "character_arc": "角色弧光不足：增加情绪变化和关系变动",
            "dialog": "对话质量偏低：增加冲突、情感表达或信息揭示",
            "consistency": "一致性有问题：检查跨章状态延续和伏笔承接",
            "engagement": "整体吸引力偏低：考虑增加冲突、悬念或情感层次",
        }
        for dim, threshold in thresholds.items():
            if scores.get(dim, 0) < threshold:
                suggestions.append(labels[dim])

        if trend == "declining":
            suggestions.append("质量趋势下降：检查是否出现了叙事疲劳（连续多章模式化）")
        if trend == "stable" and scores.get("overall", 0) < 50:
            suggestions.append("质量持续偏低：建议人工审阅粗纲和角色状态")

        return suggestions
