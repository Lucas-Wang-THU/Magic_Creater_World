# -*- coding: utf-8 -*-
"""SceneAssembler — multi-scene chapter assembly.

Detects scene boundaries from agent decision sequences, generates
transition paragraphs, and checks pacing rhythm.
"""

from __future__ import annotations

from worldforger.agents.types import AgentDecision, AgentSimResult


class SceneAssembler:
    """Assemble multiple scenes into a coherent chapter."""

    @staticmethod
    def detect_scene_boundaries(decisions: list[AgentDecision]) -> list[int]:
        """Return indices in the decision sequence where a new scene begins.

        A new scene starts when:
        - A character explicitly leaves the current location
        - The emotional tone shifts dramatically
        - A significant time gap is implied
        - A new character enters
        """
        if len(decisions) < 3:
            return []

        boundaries: list[int] = []
        for i in range(1, len(decisions)):
            d = decisions[i]
            prev = decisions[i - 1]

            # Location change signal
            location_kw = ("离开", "前往", "走向", "赶到", "抵达", "来到", "出去", "进入")
            if any(kw in (d.intended_action or "") for kw in location_kw):
                if d.character_id != prev.character_id:
                    boundaries.append(i)
                    continue

            # Emotional reset (opposite valence)
            positive_kw = ("平静", "安心", "放松", "喜悦", "温暖")
            negative_kw = ("愤怒", "恐惧", "悲伤", "紧张", "不安")
            prev_pos = any(kw in (prev.emotional_shift or "") for kw in positive_kw)
            prev_neg = any(kw in (prev.emotional_shift or "") for kw in negative_kw)
            cur_pos = any(kw in (d.emotional_shift or "") for kw in positive_kw)
            cur_neg = any(kw in (d.emotional_shift or "") for kw in negative_kw)
            if (prev_pos and cur_neg) or (prev_neg and cur_pos):
                boundaries.append(i)

        # Deduplicate near-boundaries (within 2 indices)
        filtered = []
        last = -99
        for b in boundaries:
            if b - last > 2:
                filtered.append(b)
                last = b

        return filtered

    @staticmethod
    def generate_transition(
        prev_scene_end: str,
        next_scene_start: str,
        transition_type: str = "auto",
    ) -> str:
        """Generate a transition paragraph between two scenes.

        Types:
        - time_jump: "一炷香后..." / "两个时辰后..."
        - location_shift: "他们穿过峡道，来到..."
        - emotional_bridge: "那种不安的感觉一直跟随着他，直到..."
        - abrupt: Simple separator (for intentional tonal shifts)
        """
        templates = {
            "time_jump": "时间在沉默中流逝。",
            "location_shift": "道路向前延伸，周围的景色悄然变化。",
            "emotional_bridge": "刚才的对话在他脑中回响，但他没有停下脚步。",
            "abrupt": "",
        }
        return templates.get(transition_type, "")

    @staticmethod
    def check_pacing(sim_results: list[AgentSimResult]) -> dict:
        """Check the overall pacing rhythm across scenes in a chapter.

        Returns pacing analysis: peak/valley detection, suggestions.
        """
        if len(sim_results) < 2:
            return {"rhythm": "单场景", "suggestions": []}

        # Build intensity profile from dialog quality
        from worldforger.agents.dialog_quality import DialogQuality

        intensities = []
        for sr in sim_results:
            quality = DialogQuality.assess(sr)
            intensities.append(quality["overall"])

        if not intensities:
            return {"rhythm": "未知", "suggestions": []}

        avg_intensity = sum(intensities) / len(intensities)
        suggestions: list[str] = []

        # Check for monotony (all scenes similar intensity)
        if max(intensities) - min(intensities) < 20:
            suggestions.append("节奏单一：多场景强度接近，建议增加起伏（高潮→留白→再起）")

        # Check for no peak
        if max(intensities) < 50:
            suggestions.append("缺乏高潮：所有场景强度低于50，建议至少一个冲突密集型场景")

        # Check for no valley
        if min(intensities) > 40:
            suggestions.append("缺少留白：建议减少一个高强度场景，替换为呼吸段落")

        return {
            "rhythm": "良好" if not suggestions else "需调整",
            "avg_intensity": round(avg_intensity, 1),
            "intensity_profile": intensities,
            "suggestions": suggestions,
        }
