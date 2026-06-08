"""Sentiment Tracker — per-chapter emotional tone analysis and arc visualization."""

from __future__ import annotations

import json

from worldforger.schemas import SentimentLog, World
from worldforger.story.story_store import read_sentiment_log, sentiment_path, sorted_chapters, write_sentiment_log


class SentimentTracker:
    """Tracks emotional arcs across chapters."""

    def __init__(self, world_id: str):
        self.world_id = world_id

    def load_log(self, chapter_id: str) -> SentimentLog | None:
        data = read_sentiment_log(self.world_id, chapter_id)
        if data:
            return SentimentLog.model_validate(data)
        return None

    def save_log(self, log: SentimentLog) -> None:
        write_sentiment_log(self.world_id, log.chapter_id, log.model_dump(mode="json"))

    def get_previous_ending_tone(self, world: World, chapter_id: str) -> str:
        """Get the ending tone of the chapter immediately before the given one."""
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        if not ch:
            return ""
        prev_ch = next(
            (c for c in sorted_chapters(world)
             if c.order < ch.order and c.sentiment_log),
            None
        )
        if prev_ch and prev_ch.sentiment_log:
            return prev_ch.sentiment_log.ending_tone
        return ""

    def get_all_logs(self, world: World) -> list[SentimentLog]:
        """Get all sentiment logs in chapter order, from disk or chapter model."""
        logs: list[SentimentLog] = []
        for ch in sorted_chapters(world):
            if ch.sentiment_log:
                logs.append(ch.sentiment_log)
            else:
                sl = self.load_log(ch.id)
                if sl:
                    logs.append(sl)
        return logs

    def format_previous_sentiment(self, world: World, chapter_id: str) -> str:
        """Format previous chapter ending sentiment for manuscript prompt injection."""
        ch = next((c for c in world.story.chapters if c.id == chapter_id), None)
        if not ch:
            return ""
        prev_ch = next(
            (c for c in sorted_chapters(world)
             if c.order < ch.order and c.sentiment_log),
            None
        )
        if not prev_ch or not prev_ch.sentiment_log:
            return ""
        sl = prev_ch.sentiment_log
        last_seg = sl.segments[-1] if sl.segments else None
        return (
            f"【上一章结尾情感基调】{sl.ending_tone}"
            f"（强度 {last_seg.intensity if last_seg else '?'}/10）\n"
            f"过渡评价：{sl.transition_from_prev}\n"
            "→ 本章开篇应注意情感过渡，避免突兀的基调切换（除非有意为之）。"
        )

    # ── Chart data generation ────────────────────────────────────

    def build_sentiment_arc_chart(self, world: World) -> list[dict]:
        """Build chart data for sentiment arc visualization (rendered as HTML in frontend)."""
        logs = self.get_all_logs(world)
        if not logs:
            return []

        tone_values = {
            "positive": 5, "calm": 4, "mixed": 3, "tense": 2, "negative": 1,
        }
        tone_colors = {
            "positive": "#16a34a", "calm": "#6366f1", "mixed": "#a855f7",
            "tense": "#f59e0b", "negative": "#dc2626",
        }

        points = []
        for sl in logs:
            tv = tone_values.get(sl.overall_tone, 3)
            segs = sl.segments or []
            avg_intensity = sum(s.intensity for s in segs) / len(segs) if segs else 5
            points.append({
                "chapter_id": sl.chapter_id,
                "title": sl.title or sl.chapter_id,
                "overall_tone": sl.overall_tone,
                "tone_value": tv,
                "tone_color": tone_colors.get(sl.overall_tone, "#64748b"),
                "ending_tone": sl.ending_tone,
                "avg_intensity": round(avg_intensity, 1),
            })
        return points


# ── Tone normalization: LLM often outputs Chinese labels ──
_TONE_NORMALIZE: dict[str, str] = {
    # Chinese -> English
    "积极": "positive", "正面": "positive", "乐观": "positive",
    "消极": "negative", "负面": "negative", "悲观": "negative", "悲伤": "negative",
    "紧张": "tense", "紧绷": "tense", "焦虑": "tense", "压迫": "tense",
    "平静": "calm", "平和": "calm", "宁静": "calm", "沉稳": "calm",
    "混合": "mixed", "复杂": "mixed", "混杂": "mixed",
    # Already English (passthrough)
    "positive": "positive", "negative": "negative",
    "tense": "tense", "calm": "calm", "mixed": "mixed",
}

_TRANSITION_NORMALIZE: dict[str, str] = {
    "平滑": "smooth", "顺畅": "smooth", "自然": "smooth",
    "突兀": "abrupt", "跳跃": "abrupt", "断裂": "abrupt",
    "对比": "intentional_contrast", "刻意对比": "intentional_contrast",
    "首章": "first_chapter", "第一章": "first_chapter",
    "smooth": "smooth", "abrupt": "abrupt",
    "intentional_contrast": "intentional_contrast",
    "first_chapter": "first_chapter",
}

_VALID_TONES = {"positive", "negative", "tense", "calm", "mixed"}
_VALID_TRANSITIONS = {"smooth", "abrupt", "intentional_contrast", "first_chapter"}


def _parse_sentiment(raw: str, chapter_id: str, title: str) -> SentimentLog | None:
    """Parse LLM sentiment analysis output into a SentimentLog.

    Normalizes Chinese tone/transition labels that LLMs frequently output
    despite being instructed to use English.
    """
    import re as _re
    t = raw.strip()
    if t.startswith("```"):
        t = _re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = _re.sub(r"\s*```$", "", t)
        t = t.strip()
    start = t.find("{")
    end = t.rfind("}")
    if start == -1 or end == -1:
        print(f"[MCW-SENTIMENT] ch:{chapter_id} parse failed: no JSON braces found")
        return None
    t = t[start:end + 1]
    t = _re.sub(r",(\s*[}\]])", r"\1", t)
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        print(f"[MCW-SENTIMENT] ch:{chapter_id} JSON parse error: {e}")
        return None
    if not isinstance(data, dict):
        print(f"[MCW-SENTIMENT] ch:{chapter_id} not a dict")
        return None

    # ── Normalize tone values in segments ──
    segments = data.get("segments", [])
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                raw_tone = str(seg.get("tone", "")).strip()
                seg["tone"] = _TONE_NORMALIZE.get(raw_tone, "mixed")
                # Clamp intensity
                try:
                    ival = int(seg.get("intensity", 5))
                    seg["intensity"] = max(1, min(10, ival))
                except (ValueError, TypeError):
                    seg["intensity"] = 5

    # ── Normalize overall_tone and ending_tone ──
    for key in ("overall_tone", "ending_tone"):
        raw = str(data.get(key, "")).strip()
        data[key] = _TONE_NORMALIZE.get(raw, "mixed")

    # ── Normalize transition_from_prev ──
    raw_trans = str(data.get("transition_from_prev", "")).strip()
    data["transition_from_prev"] = _TRANSITION_NORMALIZE.get(raw_trans, "first_chapter")

    data["chapter_id"] = chapter_id
    data["title"] = title
    data.setdefault("analyzed_at", "")

    try:
        return SentimentLog.model_validate(data)
    except Exception as e:
        print(f"[MCW-SENTIMENT] ch:{chapter_id} validation error: {e}")
        # Try with minimal segments as last resort
        try:
            data["segments"] = [
                {"segment_index": 1, "label": "全文", "tone": data.get("overall_tone", "mixed"),
                 "intensity": 5, "summary": "（自动生成的默认片段）"}
            ]
            return SentimentLog.model_validate(data)
        except Exception:
            return None
