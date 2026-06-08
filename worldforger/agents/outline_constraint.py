# -*- coding: utf-8 -*-
"""Macro outline constraint parser.

Extracts hard constraints (world events) and soft direction from the
macro outline for a specific chapter.  Uses a lightweight LLM call
for parsing.
"""

from __future__ import annotations

from worldforger.agents.types import OutlineConstraints
from worldforger.llm import chat_completion


class OutlineConstraint:
    """Parse and inject macro outline constraints for a chapter."""

    @staticmethod
    async def parse(macro_text: str, chapter_id: str) -> OutlineConstraints:
        """Extract structured constraints from macro outline text."""
        import json as _json
        system = (
            "你是粗纲解析器。从粗纲文本中提取结构化约束。只输出JSON。\n"
            '格式: {"hard_events":[], "hard_locations":[], '
            '"must_advance_clues":[], "soft_direction":""}\n'
            "hard_events: 本章必须发生的世界事件（不由角色意志转移）\n"
            "hard_locations: 本章必须出现的地点\n"
            "must_advance_clues: 本章必须推进的伏笔id\n"
            "soft_direction: 本章建议的叙事方向（一句话）"
        )
        user = f"粗纲文本:\n{macro_text[:4000]}\n\n目标章节: {chapter_id}"
        try:
            raw = await chat_completion(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                temperature=0.15, max_tokens=1024,
                timing_label=f"outline_parse:{chapter_id}",
            )
            data = _json.loads(raw)
            return OutlineConstraints(
                hard_events=data.get("hard_events", []),
                hard_locations=data.get("hard_locations", []),
                must_advance_clues=data.get("must_advance_clues", []),
                soft_direction=data.get("soft_direction", ""),
            )
        except Exception:
            return OutlineConstraints()

    @staticmethod
    def inject_to_scene(constraints: OutlineConstraints, scene_setup: str) -> str:
        """Inject parsed constraints into the scene setup text."""
        parts = [scene_setup]
        if constraints.hard_events:
            parts.append("\n【本章必须发生的世界事件（不可改变，只能应对）】")
            for evt in constraints.hard_events:
                parts.append(f"  - {evt}")
        if constraints.must_advance_clues:
            parts.append("\n【本章需推进的线索】")
            for clue in constraints.must_advance_clues:
                parts.append(f"  - {clue}")
        if constraints.soft_direction:
            parts.append(f"\n【叙事方向】{constraints.soft_direction}")
        return "\n".join(parts)

    @staticmethod
    def verify_completion(
        constraints: OutlineConstraints,
        manuscript_text: str,
    ) -> dict:
        """Check if hard constraints were satisfied in the generated text."""
        results = {"all_satisfied": True, "checks": []}
        for evt in constraints.hard_events:
            keywords = evt[:20]
            satisfied = keywords in manuscript_text
            results["checks"].append({"event": evt, "satisfied": satisfied})
            if not satisfied:
                results["all_satisfied"] = False
        return results
