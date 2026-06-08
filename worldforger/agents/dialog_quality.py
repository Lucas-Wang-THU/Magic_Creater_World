# -*- coding: utf-8 -*-
"""Dialog quality assessment for multi-character interactions.

Scores each scene along three axes: conflict, emotional change, and
information release.  No LLM calls — pure heuristic analysis of the
decision sequence.
"""

from __future__ import annotations

from worldforger.agents.types import AgentDecision, AgentSimResult


class DialogQuality:
    """Score a scene's dialog quality heuristically from decisions."""

    @staticmethod
    def assess(sim_result: AgentSimResult) -> dict:
        """Return a quality report with per-axis scores and suggestions."""
        decisions = sim_result.decision_sequence
        if not decisions:
            return {
                "conflict_score": 0, "emotion_score": 0,
                "info_score": 0, "overall": 0,
                "suggestions": ["场景无角色互动——建议注入外部事件或重新设计场景"],
            }

        conflict = DialogQuality._score_conflict(decisions)
        emotion = DialogQuality._score_emotion(decisions)
        info = DialogQuality._score_info(decisions)
        overall = round((conflict + emotion + info) / 3, 1)

        suggestions: list[str] = []
        if conflict < 30:
            suggestions.append("冲突不足：角色间缺乏目标对立或意见分歧")
        if emotion < 30:
            suggestions.append("情感平淡：缺少情绪变化（愤怒、恐惧、喜悦、悲伤）")
        if info < 20:
            suggestions.append("信息停滞：场景未推进任何线索或揭示新信息")

        return {
            "conflict_score": conflict,
            "emotion_score": emotion,
            "info_score": info,
            "overall": overall,
            "suggestions": suggestions if overall < 50 else [],
        }

    @staticmethod
    def _score_conflict(decisions: list[AgentDecision]) -> int:
        score = 0
        # Opposing intended_actions
        action_pairs = []
        for i, d1 in enumerate(decisions):
            for d2 in decisions[i + 1:]:
                if d1.target_character == d2.character_id and d2.target_character == d1.character_id:
                    action_pairs.append((d1, d2))
        score += min(len(action_pairs) * 20, 60)

        # Confrontation signals in actions
        confront_kw = ("对峙", "反驳", "拒绝", "质问", "威胁", "挑战", "阻止", "推开", "逼近", "逼问")
        confront_count = sum(
            1 for d in decisions
            if any(kw in (d.intended_action or "") + " " + (d.intended_speech or "") for kw in confront_kw)
        )
        score += min(confront_count * 10, 30)

        # Relationship changes (negative = conflict)
        neg_changes = sum(
            1 for d in decisions
            for v in d.relationship_changes.values()
            if "-" in v or "下降" in v or "不信任" in v
        )
        score += min(neg_changes * 5, 10)

        return min(score, 100)

    @staticmethod
    def _score_emotion(decisions: list[AgentDecision]) -> int:
        score = 0

        # Emotional shift diversity
        shifts = [d.emotional_shift for d in decisions if d.emotional_shift]
        score += min(len(shifts) * 15, 40)

        # Intensity of emotion keywords
        intense_kw = ("愤怒", "恐惧", "崩溃", "绝望", "狂喜", "暴怒", "痛苦", "哭泣", "颤抖")
        intense_count = sum(
            1 for d in decisions
            if any(kw in (d.internal_reaction or "") for kw in intense_kw)
        )
        score += min(intense_count * 10, 30)

        # Internal reaction depth (longer = more emotion)
        deep_reactions = [d for d in decisions if len(d.internal_reaction or "") > 30]
        score += min(len(deep_reactions) * 10, 30)

        return min(score, 100)

    @staticmethod
    def _score_info(decisions: list[AgentDecision]) -> int:
        score = 0

        # Hidden intents (information asymmetry)
        hidden = [d for d in decisions if d.hidden_intent and len(d.hidden_intent) > 5]
        score += min(len(hidden) * 15, 30)

        # New goals generated
        new_goals = [d for d in decisions if d.new_short_term_goal]
        score += min(len(new_goals) * 15, 30)

        # Speech containing "why"/"what"/"how" (information seeking)
        info_seek_kw = ("为什么", "怎么", "什么", "谁", "哪里", "何时", "告诉我", "解释")
        info_seek = sum(
            1 for d in decisions
            if d.intended_speech and any(kw in d.intended_speech for kw in info_seek_kw)
        )
        score += min(info_seek * 10, 20)

        # Knowledge revealed (decisions that sound like revelations)
        reveal_kw = ("原来", "其实", "真相", "秘密", "发现", "终于", "其实", "竟然")
        reveals = sum(
            1 for d in decisions
            if d.intended_speech and any(kw in d.intended_speech for kw in reveal_kw)
        )
        score += min(reveals * 10, 20)

        return min(score, 100)
