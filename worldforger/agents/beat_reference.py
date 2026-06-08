# -*- coding: utf-8 -*-
"""Beat reference extractor -- parse chapter beats as soft hints.

Beats are "suggestions" not "commands" in the agent architecture.
"""

from __future__ import annotations

from worldforger.agents.types import AgentSimResult, BeatReferenceData
from worldforger.llm import chat_completion


class BeatReference:
    """Extract soft reference hints from chapter beat markdown."""

    @staticmethod
    async def parse(beat_text: str) -> BeatReferenceData:
        """Parse beat text into structured reference data."""
        import json as _json
        system = (
            "你是细纲解析器。从细纲中提取结构化信息。只输出JSON。\n"
            '格式: {"scene_goals":["目标1"], "characters_involved":["id1"], '
            '"conflict_hints":["冲突方向1"]}\n'
            "只提取场景目标、出场人物id、冲突提示。忽略情绪走向和对话内容。"
        )
        try:
            raw = await chat_completion(
                [{"role": "system", "content": system},
                 {"role": "user", "content": beat_text[:3000]}],
                temperature=0.15, max_tokens=1024,
                timing_label="beat_parse",
            )
            data = _json.loads(raw)
            return BeatReferenceData(
                scene_goals=data.get("scene_goals", []),
                characters_involved=data.get("characters_involved", []),
                conflict_hints=data.get("conflict_hints", []),
            )
        except Exception:
            return BeatReferenceData()

    @staticmethod
    def inject_as_soft_hints(beat_ref: BeatReferenceData) -> list[str]:
        hints = []
        if beat_ref.scene_goals:
            hints.append(f"建议目标: {'; '.join(beat_ref.scene_goals[:3])}")
        if beat_ref.conflict_hints:
            hints.append(f"可能冲突: {'; '.join(beat_ref.conflict_hints[:2])}")
        return hints

    @staticmethod
    def record_deviation(
        beat_ref: BeatReferenceData, sim_result: AgentSimResult,
    ) -> str | None:
        if not beat_ref.scene_goals:
            return None
        all_actions = " ".join(
            (d.intended_action or "") + " " + (d.intended_speech or "")
            for d in sim_result.decision_sequence
        )
        missed = [g for g in beat_ref.scene_goals if g[:10] not in all_actions]
        if missed:
            return f"细纲目标未完全覆盖: {missed}。角色自然决策方向: {sim_result.decision_sequence[0].intended_action[:60] if sim_result.decision_sequence else 'N/A'}。"
        return None
