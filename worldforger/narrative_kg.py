"""Narrative Knowledge Graph — lightweight event-entity-time triples.

Tracks character state evolution and key item flow across chapters.
"""

from __future__ import annotations

from worldforger.schemas import CharacterStateSnapshot, KGEntity, KGEvent, NarrativeKG, World
from worldforger.story.story_store import read_narrative_kg, write_narrative_kg


class NarrativeKGManager:
    """Manages the Narrative Knowledge Graph for a world."""

    def __init__(self, world_id: str):
        self.world_id = world_id

    def load(self) -> NarrativeKG:
        data = read_narrative_kg(self.world_id)
        if data:
            return NarrativeKG.model_validate(data)
        return NarrativeKG()

    def save(self, kg: NarrativeKG) -> None:
        write_narrative_kg(self.world_id, kg.model_dump(mode="json"))

    # ── Query methods ──────────────────────────────────────────

    def get_character_state(self, char_id: str) -> CharacterStateSnapshot | None:
        """Get the latest state snapshot for a character."""
        kg = self.load()
        for ent in kg.entities:
            if ent.entity_id == char_id and ent.entity_type == "character" and ent.states:
                return ent.states[-1]
        return None

    def get_character_timeline(self, char_id: str) -> list[CharacterStateSnapshot]:
        """Get all state snapshots for a character in chapter order."""
        kg = self.load()
        for ent in kg.entities:
            if ent.entity_id == char_id and ent.entity_type == "character":
                return list(ent.states)
        return []

    def get_item_status(self, item_id: str) -> KGEntity | None:
        """Get current status of a tracked item."""
        kg = self.load()
        for ent in kg.entities:
            if ent.entity_id == item_id and ent.entity_type == "item":
                return ent
        return None

    def get_events_for_chapter(self, chapter_id: str) -> list[KGEvent]:
        kg = self.load()
        return [e for e in kg.events if e.chapter_id == chapter_id]

    def get_recent_events(self, n: int = 5) -> list[KGEvent]:
        kg = self.load()
        return kg.events[-n:] if kg.events else []

    # ── Update methods ─────────────────────────────────────────

    def merge_extraction(self, extracted: dict) -> NarrativeKG:
        """Merge extracted KG data from a chapter into the stored KG."""
        kg = self.load()
        entities_list: list[dict] = extracted.get("entities") or []
        events_list: list[dict] = extracted.get("events") or []
        fs_planted: list[str] = extracted.get("foreshadowing_planted") or []
        fs_resolved: list[str] = extracted.get("foreshadowing_resolved") or []

        # Merge entities
        existing_ids = {e.entity_id: i for i, e in enumerate(kg.entities)}
        for ent_dict in entities_list:
            eid = ent_dict.get("entity_id", "")
            if not eid:
                continue
            if eid in existing_ids:
                existing = kg.entities[existing_ids[eid]]
                if ent_dict.get("entity_type") == "character":
                    new_states = ent_dict.get("states") or []
                    seen_chapters = {s.chapter_id for s in existing.states}
                    for st_dict in new_states:
                        if st_dict.get("chapter_id") not in seen_chapters:
                            existing.states.append(CharacterStateSnapshot(**st_dict))
                            seen_chapters.add(st_dict["chapter_id"])
                elif ent_dict.get("entity_type") == "item":
                    if ent_dict.get("item_status"):
                        existing.item_status = ent_dict["item_status"]
                    if ent_dict.get("possessed_by"):
                        existing.possessed_by = ent_dict["possessed_by"]
                    if ent_dict.get("last_seen_chapter"):
                        existing.last_seen_chapter = ent_dict["last_seen_chapter"]
            else:
                try:
                    kg.entities.append(KGEntity(**ent_dict))
                except Exception:
                    continue

        # Merge events (dedup by event_id)
        existing_event_ids = {e.event_id for e in kg.events}
        for evt_dict in events_list:
            eid = evt_dict.get("event_id", "")
            if not eid or eid in existing_event_ids:
                continue
            try:
                kg.events.append(KGEvent(**evt_dict))
                existing_event_ids.add(eid)
            except Exception:
                continue

        # Update foreshadowing cross-reference
        for fid in fs_planted:
            if fid not in kg.foreshadowing_ids:
                kg.foreshadowing_ids.append(fid)

        self.save(kg)
        return kg

    def snapshot_character_states(self, world: World, chapter_id: str) -> list[dict]:
        """Build character state snapshots from current world state for this chapter."""
        snapshots: list[dict] = []
        for ent in world.characters.entities:
            if not isinstance(ent, dict):
                continue
            rs = ent.get("runtime_state")
            if not isinstance(rs, dict):
                continue
            snapshots.append({
                "entity_id": ent.get("id", ""),
                "entity_type": "character",
                "name": ent.get("name", ""),
                "states": [{
                    "chapter_id": chapter_id,
                    "location": rs.get("current_location", ""),
                    "emotion": rs.get("emotional_state", ""),
                    "goal": rs.get("current_goal", ""),
                }],
            })
        return snapshots

    # ── Format for prompt injection ────────────────────────────

    def format_for_prompt(self, character_ids: list[str] | None = None) -> str:
        """Format KG state for manuscript prompt."""
        kg = self.load()
        if not kg.entities:
            return ""
        lines = ["【知识图谱 — 角色当前状态（跨章节追踪）】"]
        char_entities = [
            e for e in kg.entities
            if e.entity_type == "character" and e.states
            and (character_ids is None or e.entity_id in character_ids)
        ]
        for ent in char_entities:
            latest = ent.states[-1]
            lines.append(
                f"- {ent.name}({ent.entity_id})：位于 {latest.location}，"
                f"情绪 {latest.emotion}，目标 {latest.goal}"
            )
        recent = self.get_recent_events(3)
        if recent:
            lines.append("\n最近关键事件：")
            for evt in recent:
                lines.append(f"  - [{evt.chapter_id}] {evt.event_type}: {evt.summary[:80]}")
        return "\n".join(lines) if len(lines) > 1 else ""
