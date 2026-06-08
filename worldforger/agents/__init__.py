# -*- coding: utf-8 -*-
"""Character Agent system — emergent narrative generation.

Phase 0 (Complete):
  CharacterAgent, SceneSimulator, POVFilter, StateInjector,
  OutlineConstraint, BeatReference, ContinuityChecker, AgentStore

Phase 1 (Complete):
  DialogQuality, BeatCoordinator

Phase 2 (Complete):
  WorldClock, ShadowInfluence, SceneAssembler

Phase 3 (Partial):
  QualityEvaluator, AutonomyManager, ChapterRunner, QualityBenchmark
"""

from worldforger.agents.character_agent import CharacterAgent
from worldforger.agents.scene_simulator import SceneSimulator
from worldforger.agents.pov_filter import POVFilter
from worldforger.agents.state_injector import StateInjector
from worldforger.agents.outline_constraint import OutlineConstraint
from worldforger.agents.beat_reference import BeatReference
from worldforger.agents.continuity_checker import ContinuityChecker
from worldforger.agents.agent_store import AgentStore
from worldforger.agents.dialog_quality import DialogQuality
from worldforger.agents.beat_coordinator import BeatCoordinator
from worldforger.agents.world_clock import WorldClock, WorldState, WorldEvent
from worldforger.agents.shadow_influence import ShadowInfluence
from worldforger.agents.scene_assembler import SceneAssembler
from worldforger.agents.quality_evaluator import QualityEvaluator
from worldforger.agents.autonomy import AutonomyManager, AutonomyLevel
from worldforger.agents.chapter_runner import ChapterRunner, ChapterRunResult, RunSession, QualityBenchmark

__all__ = [
    "CharacterAgent", "SceneSimulator", "POVFilter",
    "StateInjector", "OutlineConstraint", "BeatReference",
    "ContinuityChecker", "AgentStore",
    "DialogQuality", "BeatCoordinator",
    "WorldClock", "WorldState", "WorldEvent",
    "ShadowInfluence", "SceneAssembler",
    "QualityEvaluator", "AutonomyManager", "AutonomyLevel",
    "ChapterRunner", "ChapterRunResult", "RunSession", "QualityBenchmark",
]
