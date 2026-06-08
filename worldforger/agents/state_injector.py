# -*- coding: utf-8 -*-
"""Format character agent states as prompt fragments for the writer agent."""

from __future__ import annotations

from worldforger.agents.types import CharacterAgentState


class StateInjector:
    """Convert CharacterAgentState dicts into writer-agent prompt context."""

    @staticmethod
    def for_writer_agent(
        pov_state: CharacterAgentState,
        present_states: dict[str, CharacterAgentState],
        shadow_states: dict[str, CharacterAgentState],
    ) -> str:
        parts = ["\n【角色当前状态（从上一章延续，不可矛盾）】\n"]
        parts.append(f"## POV 角色：{pov_state.name}")
        parts.append(f"- 位置: {pov_state.current_location}")
        parts.append(f"- 情绪: {pov_state.emotional_state}")
        parts.append(f"- 目标: {pov_state.current_goal}")
        if pov_state.active_aftermaths:
            parts.append("- 活跃后遗症:")
            for am in pov_state.active_aftermaths:
                parts.append(f"  - {am.get('source_event','')}: 强度{am.get('intensity',0)}/10 — {', '.join(am.get('symptoms',[])[:3])}")
        injuries = pov_state.physical_state.get("active_injuries", []) if pov_state.physical_state else []
        if injuries:
            parts.append(f"- 身体: {', '.join(injuries[:3])}")
        if pov_state.relationships:
            parts.append("- 关系变化:")
            for tid, rel in list(pov_state.relationships.items())[:5]:
                if rel.get("last_change"):
                    parts.append(f"  - {tid}: {rel['last_change']}")

        if present_states:
            parts.append("\n## 在场角色")
            for cid, s in present_states.items():
                parts.append(f"- {s.name}: {s.emotional_state or '平稳'}。目标: {s.current_goal or '未知'}")

        if shadow_states:
            parts.append("\n## 离线角色（作家参考——不要在正文中直接描写其行动）")
            for cid, s in shadow_states.items():
                parts.append(f"- {s.name}: 位置={s.current_location}, 目标={s.current_goal}")

        return "\n".join(parts)

    @staticmethod
    def for_character_agent(state: CharacterAgentState) -> str:
        parts = [
            f"你是{state.name}。",
            f"你想要: {state.core_desire}",
            f"你害怕: {state.core_fear}",
            f"当前情绪: {state.emotional_state}",
            f"当前目标: {state.current_goal}",
        ]
        if state.active_aftermaths:
            parts.append("旧伤:")
            for am in state.active_aftermaths[:3]:
                parts.append(f"  - {am.get('source_event','')}: {', '.join(am.get('symptoms',[])[:3])}")
        return "\n".join(parts)
