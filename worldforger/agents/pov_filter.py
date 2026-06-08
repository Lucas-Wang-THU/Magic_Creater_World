# -*- coding: utf-8 -*-
"""Single-POV filter -- extract only what the viewpoint character can perceive."""

from __future__ import annotations

from worldforger.agents.types import AgentDecision


class POVFilter:
    """Deterministic rule engine that filters a full simulation to POV-visible events.

    No LLM calls -- pure rule-based filtering.
    """

    @staticmethod
    def filter(decisions: list[AgentDecision], pov_id: str) -> list[str]:
        """Convert a decision sequence into POV-visible event descriptions."""
        events: list[str] = []

        for d in decisions:
            if d.character_id == pov_id:
                # POV character's own experience -- full access
                events.append(f"[内心] {d.internal_reaction}")
                if d.intended_speech and d.target_character:
                    events.append(
                        f"[对话→{d.target_character}] {d.intended_speech}"
                    )
                elif d.intended_action:
                    events.append(f"[行动] {d.intended_action}")
                if d.emotional_shift:
                    events.append(f"[情绪] {d.emotional_shift}")

            elif d.target_character == pov_id:
                # Another character addresses or acts toward the POV character
                if d.intended_speech:
                    events.append(f"[{d.character_id}→你] {d.intended_speech}")
                elif d.intended_action:
                    events.append(f"[{d.character_id}→你] {d.intended_action}")

            elif d.target_character and d.target_character != pov_id:
                # Interaction between other characters -- POV character observes
                if d.intended_speech or d.intended_action:
                    action = d.intended_speech or d.intended_action
                    events.append(
                        f"[旁观] {d.character_id} → {d.target_character}: {action}"
                    )

            else:
                # Untargeted action -- POV character may notice
                if d.intended_action:
                    events.append(f"[观察到] {d.character_id} {d.intended_action}")

        return events

    @staticmethod
    def annotate_reader_knowledge(
        pov_visible: list[str],
        shadow_events: list[str],
        foreshadowing: list,
    ) -> str:
        """Generate hints for the writer about what readers might suspect."""
        hints = []
        for shadow in shadow_events:
            for fs in foreshadowing:
                label = getattr(fs, "label", "") if hasattr(fs, "label") else fs.get("label", "")
                notes = getattr(fs, "notes", "") if hasattr(fs, "notes") else fs.get("notes", "")
                if label and any(kw in shadow for kw in (label, notes)):
                    hints.append(
                        f"读者可能注意到: 伏笔'{label}'与幕后事件'{shadow[:80]}'呼应。"
                        f"可在环境描写中给隐晦暗示。"
                    )
                    break
        return "\n".join(hints) if hints else ""
