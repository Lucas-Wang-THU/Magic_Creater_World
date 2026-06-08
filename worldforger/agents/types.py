# -*- coding: utf-8 -*-
"""Agent system data models.

These models define the structured outputs of character agent decisions,
simulation results, and persistable agent state.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentDecision(BaseModel):
    """A single decision made by a character agent in one round of a scene."""

    character_id: str = ""
    decision_round: int = 0
    internal_reaction: str = ""
    emotional_shift: str = ""
    intended_action: str = ""
    intended_speech: str | None = None
    target_character: str | None = None
    hidden_intent: str = ""
    relationship_changes: dict[str, str] = Field(default_factory=dict)
    new_short_term_goal: str | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class AgentSimResult(BaseModel):
    """Complete result of a single-scene multi-character simulation."""

    chapter_id: str = ""
    scene_index: int = 0
    macro_events: list[str] = Field(default_factory=list)
    decision_sequence: list[AgentDecision] = Field(default_factory=list)
    pov_visible_events: list[str] = Field(default_factory=list)
    shadow_events: list[str] = Field(default_factory=list)
    beat_deviation: str | None = None


class CharacterAgentState(BaseModel):
    """Fully persistable state of one character agent."""

    character_id: str = ""
    name: str = ""
    speech_profile: dict[str, Any] = Field(default_factory=dict)
    core_desire: str = ""
    core_fear: str = ""
    flaws: list[dict[str, Any]] = Field(default_factory=list)
    current_location: str = ""
    current_goal: str = ""
    emotional_state: str = ""
    physical_state: dict[str, Any] = Field(default_factory=dict)
    active_aftermaths: list[dict[str, Any]] = Field(default_factory=list)
    pressure_level: int = 0
    relationships: dict[str, dict[str, Any]] = Field(default_factory=dict)
    knowledge_boundary: dict[str, str] = Field(default_factory=dict)
    recent_memories: list[dict[str, Any]] = Field(default_factory=list)
    last_chapter: str = ""
    total_decisions_made: int = 0


class OutlineConstraints(BaseModel):
    """Parsed constraints from a macro outline chapter entry."""

    hard_events: list[str] = Field(default_factory=list)
    hard_locations: list[str] = Field(default_factory=list)
    must_advance_clues: list[str] = Field(default_factory=list)
    soft_direction: str = ""


class BeatReferenceData(BaseModel):
    """Parsed reference info from a chapter beat file."""

    scene_goals: list[str] = Field(default_factory=list)
    characters_involved: list[str] = Field(default_factory=list)
    conflict_hints: list[str] = Field(default_factory=list)


class ContinuityReport(BaseModel):
    """Pre-generation continuity check results."""

    warnings: list[str] = Field(default_factory=list)
    passed: bool = True
