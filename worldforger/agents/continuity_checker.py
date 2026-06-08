# -*- coding: utf-8 -*-
"""Cross-chapter state continuity verification.

Runs before and after each chapter generation to ensure
character states carry forward correctly.
"""

from __future__ import annotations

from worldforger.agents.types import (
    AgentDecision, AgentSimResult, CharacterAgentState, ContinuityReport,
)


class ContinuityChecker:
    """Automatic cross-chapter state continuity checks."""

    @staticmethod
    def pre_generation_check(
        prev_states: dict[str, CharacterAgentState],
        scene_setup: str,
        pov_id: str | None = None,
    ) -> ContinuityReport:
        """Verify previous-chapter state is properly carried into this chapter."""
        warnings: list[str] = []

        for char_id, state in prev_states.items():
            # Check location continuity for POV character
            if pov_id and char_id == pov_id and state.current_location:
                if state.current_location not in scene_setup:
                    warnings.append(
                        f"[位置] {state.name}: 上一章在'{state.current_location}'，"
                        f"本章场景中未提及。需在章节开头说明移动过程。"
                    )

            # Check active aftermaths
            for am in state.active_aftermaths:
                if am.get("intensity", 0) >= 4:
                    warnings.append(
                        f"[后遗症] {state.name}: '{am.get('source_event','')}' "
                        f"强度{am.get('intensity')}/10，本章应至少有1处体现。"
                    )

            # Check physical state
            injuries = state.physical_state.get("active_injuries", []) if state.physical_state else []
            if injuries:
                warnings.append(
                    f"[身体] {state.name}: 仍受伤: {', '.join(injuries[:3])}。不应突然痊愈。"
                )

        return ContinuityReport(
            warnings=warnings,
            passed=len(warnings) == 0,
        )

    @staticmethod
    def post_generation_update(
        sim_result: AgentSimResult,
        prev_states: dict[str, CharacterAgentState],
    ) -> dict[str, CharacterAgentState]:
        """Update all agent states based on the simulation results."""
        new_states: dict[str, CharacterAgentState] = {}

        for char_id, prev in prev_states.items():
            new = prev.model_copy(deep=True)
            char_decisions = [
                d for d in sim_result.decision_sequence
                if d.character_id == char_id
            ]

            if not char_decisions:
                new = ContinuityChecker._apply_natural_decay(new)
                new_states[char_id] = new
                continue

            last_d = char_decisions[-1]
            if last_d.emotional_shift:
                new.emotional_state = last_d.emotional_shift
            for target_id, change_desc in last_d.relationship_changes.items():
                if target_id not in new.relationships:
                    new.relationships[target_id] = {}
                new.relationships[target_id]["last_change"] = change_desc
            if last_d.new_short_term_goal:
                new.current_goal = last_d.new_short_term_goal

            new.last_chapter = sim_result.chapter_id
            new.total_decisions_made += len(char_decisions)
            new.pressure_level = min(100, new.pressure_level + 3)  # slight increase
            new_states[char_id] = new

        return new_states

    @staticmethod
    def _apply_natural_decay(state: CharacterAgentState) -> CharacterAgentState:
        """Apply natural decay to off-screen character states."""
        for am in state.active_aftermaths:
            decay = am.get("decay_rate", 0.3)
            intensity = max(1, am.get("intensity", 5) - decay)
            am["intensity"] = intensity
            if intensity <= 2:
                am["current_status"] = "dormant"
        state.pressure_level = max(0, state.pressure_level - 3)
        return state
