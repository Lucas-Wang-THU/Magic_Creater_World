# -*- coding: utf-8 -*-
"""Beat deviation quantification and auto-coordination.

When character agent decisions diverge from the chapter beat plan,
classify the deviation severity and suggest automatic responses.
"""

from __future__ import annotations

from enum import Enum

from worldforger.agents.types import AgentDecision, AgentSimResult, BeatReferenceData


class DeviationSeverity(str, Enum):
    NONE = "none"          # Perfect alignment
    LIGHT = "light"        # Minor difference, auto-accept
    MODERATE = "moderate"  # Noticeable divergence, log + adjust next chapter
    SEVERE = "severe"      # Hard constraint violation, needs retry or human


class BeatCoordinator:
    """Quantify and respond to beat deviations."""

    @staticmethod
    def classify_deviation(
        beat_ref: BeatReferenceData,
        sim_result: AgentSimResult,
    ) -> dict:
        """Classify how much the agent simulation diverged from the beat plan.

        Returns a dict with severity, details, and recommended action.
        """
        if not beat_ref.scene_goals:
            return {"severity": DeviationSeverity.NONE, "details": "无细纲目标，无需检测偏离"}

        decisions = sim_result.decision_sequence
        if not decisions:
            return {"severity": DeviationSeverity.SEVERE, "details": "角色无任何决策——场景模拟失败"}

        all_actions = " ".join(
            (d.intended_action or "") + " " + (d.intended_speech or "")
            for d in decisions
        )

        # Check each scene goal
        goal_results = []
        for goal in beat_ref.scene_goals:
            # Extract key terms: first check the full short goal as substring,
            # then try sliding 2-3 char windows as fallback for partial matches
            short_goal = goal[:20].replace(" ", "").replace("的", "").replace("了", "")
            anchor = short_goal[:6] if len(short_goal) >= 6 else short_goal
            # Try anchor match first (exact substring)
            matched = anchor in all_actions
            # If anchor fails, try any 2-char sliding window
            if not matched and len(short_goal) >= 3:
                windows = [short_goal[j:j+3] for j in range(len(short_goal) - 2)]
                matched = any(w in all_actions for w in windows[:8])
            # Last resort: try each individual 2-char bigram
            if not matched and len(short_goal) >= 2:
                bigrams = [short_goal[j:j+2] for j in range(len(short_goal) - 1)]
                matched = any(b in all_actions for b in bigrams[:5])
            goal_results.append({
                "goal": goal,
                "matched": matched,
                "anchor": anchor,
            })

        missed = [g for g in goal_results if not g["matched"]]
        matched = [g for g in goal_results if g["matched"]]
        match_rate = len(matched) / len(goal_results) if goal_results else 1.0

        # Determine severity
        if match_rate >= 0.8:
            severity = DeviationSeverity.LIGHT
            action = "auto_accept"
            detail = f"细纲目标匹配率 {match_rate:.0%}（{len(matched)}/{len(goal_results)}），轻度偏离，自动采纳"
        elif match_rate >= 0.5:
            severity = DeviationSeverity.MODERATE
            action = "log_and_adjust"
            detail = (
                f"细纲目标匹配率 {match_rate:.0%}（{len(matched)}/{len(goal_results)}），"
                f"未匹配: {[g['goal'][:40] for g in missed]}。角色实际方向: "
                f"{decisions[0].intended_action[:60] if decisions else 'N/A'}。"
                f"建议: 下一章增加软提示引导角色靠近剩余目标。"
            )
        elif match_rate > 0:
            severity = DeviationSeverity.MODERATE
            action = "log_and_adjust"
            detail = (
                f"细纲目标匹配率仅 {match_rate:.0%}，角色大幅偏离细纲。"
                f"建议: 检查粗纲硬约束是否仍满足，如满足则接受涌现方向。"
            )
        else:
            # Check if macro constraints are still met
            macro_ok = bool(sim_result.macro_events)
            if macro_ok:
                severity = DeviationSeverity.MODERATE
                action = "log_and_accept"
                detail = "细纲目标完全偏离，但粗纲硬约束仍满足——接受角色涌现方向。"
            else:
                severity = DeviationSeverity.SEVERE
                action = "retry_or_human"
                detail = "细纲目标完全偏离且粗纲硬约束未被满足——需要人工介入或自动重试。"

        return {
            "severity": severity,
            "action": action,
            "detail": detail,
            "match_rate": match_rate,
            "missed_goals": [g["goal"] for g in missed],
            "matched_goals": [g["goal"] for g in matched],
            "suggested_prompt_hint": BeatCoordinator._build_prompt_hint(missed, decisions) if missed else "",
        }

    @staticmethod
    def _build_prompt_hint(
        missed_goals: list[dict],
        decisions: list[AgentDecision],
    ) -> str:
        """Build a soft prompt hint for the next chapter to guide characters back."""
        if not missed_goals:
            return ""
        goals_text = "；".join(g["goal"][:50] for g in missed_goals[:3])
        return (
            f"【上一章未覆盖的细纲目标（软提示，仅供参考）】\n"
            f"上一章角色决策方向与细纲存在偏差，以下目标有待后续章节补足：\n"
            f"{goals_text}\n"
            f"建议在本章中以自然方式引入这些元素，避免强制插入。"
        )

    @staticmethod
    def should_retry(result: dict) -> bool:
        """Check if the deviation is severe enough to warrant a retry."""
        return result.get("severity") == DeviationSeverity.SEVERE

    @staticmethod
    def should_warn(result: dict) -> bool:
        """Check if the deviation merits a human-visible warning."""
        return result.get("severity") in (DeviationSeverity.MODERATE, DeviationSeverity.SEVERE)
