# -*- coding: utf-8 -*-
"""Agent state persistence to disk.

Layout:
  worlds/{world_id}/agents/{character_id}/
    agent_state.json       -- latest state snapshot
    decision_log.jsonl     -- append-only decision history
    state_history/         -- per-chapter snapshots
"""

from __future__ import annotations

import json as _json
from pathlib import Path

from worldforger.agents.types import AgentDecision, CharacterAgentState


def _agents_dir(world_id: str) -> Path:
    return Path("worlds") / world_id / "agents"


class AgentStore:
    """Read/write character agent states to/from disk."""

    @staticmethod
    def save_state(world_id: str, state: CharacterAgentState) -> None:
        dir_path = _agents_dir(world_id) / state.character_id
        dir_path.mkdir(parents=True, exist_ok=True)
        state_path = dir_path / "agent_state.json"
        state_path.write_text(
            state.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
        )
        # Also save chapter snapshot
        if state.last_chapter:
            hist_dir = dir_path / "state_history"
            hist_dir.mkdir(parents=True, exist_ok=True)
            (hist_dir / f"{state.last_chapter}.json").write_text(
                state.model_dump_json(indent=2, exclude_none=True), encoding="utf-8"
            )

    @staticmethod
    def load_state(world_id: str, character_id: str) -> CharacterAgentState | None:
        state_path = _agents_dir(world_id) / character_id / "agent_state.json"
        if not state_path.is_file():
            return None
        return CharacterAgentState.model_validate(
            _json.loads(state_path.read_text(encoding="utf-8"))
        )

    @staticmethod
    def load_all_states(world_id: str) -> dict[str, CharacterAgentState]:
        agents_root = _agents_dir(world_id)
        if not agents_root.is_dir():
            return {}
        states = {}
        for child in agents_root.iterdir():
            if child.is_dir():
                state = AgentStore.load_state(world_id, child.name)
                if state:
                    states[child.name] = state
        return states

    @staticmethod
    def append_decision_log(
        world_id: str, character_id: str, chapter_id: str,
        decisions: list[AgentDecision],
    ) -> None:
        log_path = _agents_dir(world_id) / character_id / "decision_log.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            for d in decisions:
                entry = {
                    "chapter_id": chapter_id,
                    "round": d.decision_round,
                    "decision": d.model_dump(mode="json"),
                }
                f.write(_json.dumps(entry, ensure_ascii=False) + "\n")

    @staticmethod
    def init_states_from_world(
        world_id: str, world,
    ) -> dict[str, CharacterAgentState]:
        """Initialize agent states from world.json on first use."""
        from worldforger.agents.types import CharacterAgentState as CAS
        states: dict[str, CAS] = {}
        for ent in world.characters.entities:
            if not isinstance(ent, dict):
                continue
            cid = ent.get("id", "")
            if not cid:
                continue

            arc = next(
                (a for a in getattr(world, 'character_arcs', [])
                 if getattr(a, 'character_id', '') == cid), None
            )
            pressure = next(
                (p for p in getattr(world, 'character_pressures', [])
                 if getattr(p, 'character_id', '') == cid), None
            )
            runtime = ent.get("runtime_state", {}) or {}

            state = CAS(
                character_id=cid,
                name=ent.get("name", ""),
                speech_profile=ent.get("speech_profile", {}),
                core_desire=getattr(arc, 'core_desire', '') if arc else "",
                core_fear=getattr(arc, 'core_fear', '') if arc else "",
                flaws=[
                    f.model_dump() if hasattr(f, 'model_dump') else f
                    for f in getattr(world, 'character_flaws', [])
                    if (getattr(f, 'character_id', '') if hasattr(f, 'character_id') else f.get('character_id', '')) == cid
                ],
                current_location=runtime.get("current_location", ""),
                current_goal=runtime.get("current_goal", ""),
                emotional_state=runtime.get("emotional_state", ""),
                physical_state=next(
                    (ps.model_dump() if hasattr(ps, 'model_dump') else ps
                     for ps in getattr(world, 'character_physical_states', [])
                     if (getattr(ps, 'character_id', '') if hasattr(ps, 'character_id') else ps.get('character_id', '')) == cid
                    ), {}
                ),
                active_aftermaths=[
                    am.model_dump() if hasattr(am, 'model_dump') else am
                    for am in getattr(world, 'character_aftermaths', [])
                    if (getattr(am, 'character_id', '') if hasattr(am, 'character_id') else am.get('character_id', '')) == cid
                    and (getattr(am, 'current_status', '') if hasattr(am, 'current_status') else am.get('current_status', '')) == "active"
                ],
                pressure_level=getattr(pressure, 'current_pressure', 0) if pressure else 0,
            )
            states[cid] = state
        return states
