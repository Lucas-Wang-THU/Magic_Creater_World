# -*- coding: utf-8 -*-
"""CharacterAgent -- LLM-driven decision engine for a single character.

Each important character gets one CharacterAgent instance.  The agent
wraps the character's persistent state and provides the ``decide()``
method which calls the LLM to produce a single decision.
"""

from __future__ import annotations

from worldforger.agents.types import AgentDecision, CharacterAgentState
from worldforger.agents.character_prompts import (
    build_character_system_prompt,
    build_character_perception_prompt,
)
from worldforger.llm import chat_completion


class CharacterAgent:
    """A single character's LLM-driven decision engine."""

    def __init__(self, state: CharacterAgentState, base_temperature: float = 0.55):
        self.state = state
        self.base_temp = base_temperature

    async def decide(
        self,
        scene_context: str,
        macro_events: list[str],
        previous_decisions: list[AgentDecision],
        round_index: int = 0,
    ) -> AgentDecision:
        """Perceive the current scene and make one decision.

        This is the atomic operation of the emergence system.
        Each character calls this independently with only the
        information it can perceive.
        """
        system_prompt = build_character_system_prompt(self.state)
        user_prompt = build_character_perception_prompt(
            self.state, scene_context, macro_events,
            previous_decisions, round_index,
        )

        temp = self._adjusted_temperature(scene_context)
        raw = await chat_completion(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            temperature=temp,
            max_tokens=1024,
            timing_label=f"agent:{self.state.character_id}:r{round_index}",
        )

        return self._parse_decision(raw, round_index)

    def _adjusted_temperature(self, scene_context: str) -> float:
        ctx = scene_context + " "
        high_stress_kw = ("战斗", "死亡", "深渊", "塑脉暴走", "山魈", "追杀", "崩塌")
        conflict_kw = ("对峙", "冲突", "质问", "审问", "逼问", "威胁")
        trauma_kw = ("噩梦", "幻觉", "后遗症", "触发", "碎片", "低语")

        if any(kw in ctx for kw in high_stress_kw):
            return min(self.base_temp + 0.2, 0.85)
        if any(kw in ctx for kw in conflict_kw):
            return min(self.base_temp + 0.1, 0.75)
        if any(kw in ctx for kw in trauma_kw):
            return min(self.base_temp + 0.15, 0.80)
        return self.base_temp

    def _parse_decision(self, raw: str, round_index: int) -> AgentDecision:
        import json as _json
        from worldforger.story.story_service import _repair_llm_json

        try:
            t = _repair_llm_json(raw)
            data = _json.loads(t)
        except (_json.JSONDecodeError, ValueError):
            # Fallback: minimal decision
            return AgentDecision(
                character_id=self.state.character_id,
                decision_round=round_index,
                internal_reaction="（不确定该如何反应）",
                intended_action="沉默，继续观察",
            )

        return AgentDecision(
            character_id=self.state.character_id,
            decision_round=round_index,
            internal_reaction=str(data.get("internal_reaction", "")),
            emotional_shift=str(data.get("emotional_shift", "")),
            intended_action=str(data.get("intended_action", "")),
            intended_speech=data.get("intended_speech"),
            target_character=data.get("target_character"),
            hidden_intent=str(data.get("hidden_intent", "")),
            relationship_changes=data.get("relationship_changes") or {},
            new_short_term_goal=data.get("new_short_term_goal"),
        )
