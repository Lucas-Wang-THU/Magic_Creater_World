# -*- coding: utf-8 -*-
"""Multi-chapter semi-autonomous runner.

Advances through the macro outline, generating chapters sequentially
with character agents, quality evaluation, and autonomy-based intervention.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from worldforger.agents.autonomy import AutonomyLevel, AutonomyManager
from worldforger.agents.world_clock import WorldClock, WorldState
from worldforger.agents.quality_evaluator import QualityEvaluator


@dataclass
class ChapterRunResult:
    """Result of generating a single chapter in autonomous mode."""
    chapter_id: str = ""
    chapter_order: int = 0
    success: bool = False
    manuscript_length: int = 0
    quality: dict | None = None
    deviation: dict | None = None
    intervention_needed: bool = False
    intervention_reason: str = ""
    error: str = ""


@dataclass
class RunSession:
    """State of a multi-chapter autonomous run."""
    world_id: str = ""
    chapters_completed: int = 0
    chapters_failed: int = 0
    results: list[ChapterRunResult] = field(default_factory=list)
    world_clock: WorldClock | None = None
    stopped: bool = False
    stop_reason: str = ""


class ChapterRunner:
    """Generate multiple chapters semi-autonomously.

    Uses the macro outline for chapter-level guidance while letting
    character agents drive scene-level decisions.  Pauses when
    AutonomyManager signals intervention is needed.
    """

    def __init__(
        self,
        world_id: str,
        autonomy_level: AutonomyLevel = AutonomyLevel.SEMI_AUTO,
        max_chapters: int = 5,
        stop_on_intervention: bool = True,
    ):
        self.world_id = world_id
        self.autonomy_level = autonomy_level
        self.max_chapters = max_chapters
        self.stop_on_intervention = stop_on_intervention
        self.session = RunSession(world_id=world_id)

    async def run(
        self,
        world,
        chapter_ids: list[str],
        generate_fn,  # async callable: generate_fn(world, chapter_id) -> (text, hook_errors, timing)
    ) -> RunSession:
        """Run generation for a sequence of chapters.

        Args:
            world: The World model instance
            chapter_ids: Ordered list of chapter IDs to generate
            generate_fn: Async function to call for each chapter
        """
        clock = WorldClock()
        self.session.world_clock = clock
        prev_quality = None

        for ch in world.story.chapters:
            if ch.id not in chapter_ids:
                continue
            if self.session.chapters_completed >= self.max_chapters:
                self.session.stop_reason = f"Reached max_chapters limit ({self.max_chapters})"
                self.session.stopped = True
                break

            result = ChapterRunResult(
                chapter_id=ch.id, chapter_order=ch.order,
            )

            try:
                # Generate the chapter
                text, hook_errors, timing = await generate_fn(world, ch.id)

                if text and len(text.strip()) > 200:
                    result.success = True
                    result.manuscript_length = len(text)

                    # Quality evaluation
                    continuity_issues = len(hook_errors) if hook_errors else 0
                    from worldforger.agents.types import AgentSimResult
                    sim = AgentSimResult(chapter_id=ch.id, decision_sequence=[])
                    result.quality = QualityEvaluator.evaluate(
                        sim, prev_quality=prev_quality,
                        continuity_issues=continuity_issues,
                    )
                    prev_quality = {"overall": result.quality["overall"]}

                    # Check if intervention needed
                    deviation_severity = "none"  # default
                    result.intervention_needed = AutonomyManager.should_intervene(
                        self.autonomy_level, deviation_severity,
                        result.quality["overall"],
                    )
                    if result.intervention_needed:
                        result.intervention_reason = (
                            f"Quality {result.quality['overall']}/100 below threshold "
                            f"for {self.autonomy_level.value} autonomy"
                        )
                        if self.stop_on_intervention:
                            self.session.stop_reason = result.intervention_reason
                            self.session.stopped = True

                else:
                    result.success = False
                    result.error = "Generated text too short (<200 chars)"
                    self.session.chapters_failed += 1

            except Exception as e:
                result.success = False
                result.error = str(e)
                self.session.chapters_failed += 1

            self.session.results.append(result)
            self.session.chapters_completed += 1

            # Advance world clock
            clock.advance_chapter(ch.order)

            if self.session.stopped:
                break

        return self.session

    def summary(self) -> str:
        """Return a human-readable summary of the run."""
        s = self.session
        lines = [
            f"=== Autonomous Run Summary ===",
            f"World: {s.world_id}",
            f"Autonomy: {self.autonomy_level.value}",
            f"Completed: {s.chapters_completed} | Failed: {s.chapters_failed}",
            f"Stopped: {s.stopped} ({s.stop_reason or 'N/A'})",
            f"",
            f"Per-chapter results:",
        ]
        for r in s.results:
            status = "OK" if r.success else f"FAIL ({r.error})"
            quality_str = f" Q={r.quality['overall']:.0f}/{r.quality['grade']}" if r.quality else ""
            lines.append(
                f"  {r.chapter_id} (ch{r.chapter_order}): {status} "
                f"len={r.manuscript_length}{quality_str}"
            )
            if r.intervention_needed:
                lines.append(f"    INTERVENTION: {r.intervention_reason}")
        return "\n".join(lines)


# ── Quality benchmark ──────────────────────────────────────────────

class QualityBenchmark:
    """Compare agent-generated chapter quality against a baseline.

    The baseline can be human-written chapters or previous agent runs.
    """

    @staticmethod
    def compare(
        current_quality: dict,
        baseline_quality: dict,
    ) -> dict:
        """Compare current quality scores against a baseline.

        Returns delta per dimension and an overall assessment.
        """
        if not baseline_quality or "scores" not in baseline_quality:
            return {"compared": False, "reason": "No baseline data available"}

        deltas = {}
        for dim in QualityEvaluator.DIMENSIONS:
            cur = current_quality.get("scores", {}).get(dim, 0)
            base = baseline_quality.get("scores", {}).get(dim, 0)
            deltas[dim] = round(cur - base, 1)

        overall_delta = round(
            current_quality.get("overall", 0) - baseline_quality.get("overall", 0), 1
        )

        assessment = "comparable"
        if overall_delta > 10:
            assessment = "better"
        elif overall_delta < -10:
            assessment = "worse"

        return {
            "compared": True,
            "overall_delta": overall_delta,
            "dimension_deltas": deltas,
            "assessment": assessment,
            "current_grade": current_quality.get("grade", "?"),
            "baseline_grade": baseline_quality.get("grade", "?"),
        }

    @staticmethod
    def build_baseline_from_chapters(
        chapter_qualities: list[dict],
    ) -> dict:
        """Build a baseline quality profile from a list of chapter quality dicts."""
        if not chapter_qualities:
            return {}

        scores = {dim: [] for dim in QualityEvaluator.DIMENSIONS}
        overalls = []

        for q in chapter_qualities:
            for dim in QualityEvaluator.DIMENSIONS:
                s = q.get("scores", {}).get(dim, 0)
                scores[dim].append(s)
            overalls.append(q.get("overall", 0))

        avg_scores = {
            dim: round(sum(vals) / len(vals), 1) if vals else 0
            for dim, vals in scores.items()
        }
        avg_overall = round(sum(overalls) / len(overalls), 1) if overalls else 0

        # Simple grade from average
        if avg_overall >= 75:
            grade = "A"
        elif avg_overall >= 60:
            grade = "B"
        elif avg_overall >= 45:
            grade = "C"
        elif avg_overall >= 30:
            grade = "D"
        else:
            grade = "F"

        return {
            "scores": avg_scores,
            "overall": avg_overall,
            "grade": grade,
            "sample_size": len(chapter_qualities),
        }
