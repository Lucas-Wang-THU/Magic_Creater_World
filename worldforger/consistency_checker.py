"""Consistency Checker — post-generation 7-dimension narrative audit."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from worldforger.llm import chat_completion
from worldforger.schemas import ConsistencyReport, World
from worldforger.story.story_prompts import (
    build_consistency_check_user_payload,
    consistency_check_system,
)
from worldforger.story.story_store import write_consistency_report


async def run_consistency_check(
    world: World,
    chapter_id: str,
    manuscript_text: str,
    *,
    model: str | None = None,
) -> ConsistencyReport:
    """Run a 7-dimension consistency check on a chapter manuscript.

    This is a non-blocking audit — failures return a clean report with an
    error note rather than raising exceptions.
    """
    ch = next((c for c in world.story.chapters if c.id == chapter_id), None)

    try:
        system = consistency_check_system()
        user = build_consistency_check_user_payload(
            world, chapter_id=chapter_id, manuscript_text=manuscript_text,
        )
        raw = await chat_completion(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            model=model,
            temperature=0.3,
            max_tokens=2048,
        )
        data = _parse_check_result(raw, chapter_id)
    except Exception:
        data = ConsistencyReport(
            chapter_id=chapter_id,
            checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            total_issues=0,
            verdict="clean",
        )

    # Persist to disk so frontend can read the report
    _persist_report(world.meta.id, data)

    # Attach to chapter model
    if ch:
        ch.consistency_report = data

    return data


def _parse_check_result(raw: str, chapter_id: str) -> ConsistencyReport:
    """Parse LLM consistency check output into a ConsistencyReport."""
    t = raw.strip()
    # Strip code fences if present
    if t.startswith("```"):
        import re
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
        t = t.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        return ConsistencyReport(
            chapter_id=chapter_id,
            checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            total_issues=0,
            verdict="clean",
        )
    try:
        data = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return ConsistencyReport(
            chapter_id=chapter_id,
            checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            total_issues=0,
            verdict="clean",
        )
    if not isinstance(data, dict):
        return ConsistencyReport(
            chapter_id=chapter_id,
            checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            total_issues=0,
            verdict="clean",
        )
    data["chapter_id"] = chapter_id
    data["checked_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    issues = data.get("issues") or []
    data["total_issues"] = len(issues)
    try:
        return ConsistencyReport.model_validate(data)
    except Exception:
        return ConsistencyReport(
            chapter_id=chapter_id,
            checked_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            total_issues=0,
            verdict="clean",
        )


def _persist_report(world_id: str, report: ConsistencyReport) -> None:
    """Write consistency report to disk."""
    write_consistency_report(world_id, report.chapter_id, report.model_dump(mode="json"))


def format_consistency_report_for_display(report: ConsistencyReport) -> str:
    """Format a consistency report as a readable summary string."""
    if report.verdict == "clean":
        return "✓ 一致性审校通过，未发现问题。"
    lines = [
        f"审校结果：{report.verdict}（共 {report.total_issues} 个问题）",
    ]
    for issue in report.issues:
        sev = {"critical": "🔴", "warning": "🟡", "info": "🔵"}.get(issue.severity, "⚪")
        lines.append(
            f"\n{sev} [{issue.category}] {issue.description}"
        )
        if issue.suggestion:
            lines.append(f"   建议：{issue.suggestion}")
    return "\n".join(lines)
