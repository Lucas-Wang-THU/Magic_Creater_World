from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Meta(BaseModel):
    id: str
    name: str
    genre_tags: list[str] = Field(default_factory=list)
    creative_mode: str | None = Field(
        default=None,
        description="创作载体：novel | game | coc | dnd；与前端创作模式一致。",
    )
    version: int = 1
    updated_at: str = ""
    locale: str = "zh-CN"
    rules_profile: str | None = None

    @field_validator("updated_at", mode="before")
    @classmethod
    def default_updated(cls, v: str) -> str:
        return v or _utc_now_iso()


class GeographySection(BaseModel):
    summary: str = ""
    regions: list[dict[str, Any]] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    climate_notes: str = ""
    resources: list[str] = Field(default_factory=list)
    map_notes: str = ""


class PowerTier(BaseModel):
    name: str
    description: str = ""
    typical_capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)


class PowerSystem(BaseModel):
    summary: str = ""
    tiers: list[PowerTier] = Field(default_factory=list)


class ItemGrade(BaseModel):
    name: str
    rarity_narrative: str = ""
    typical_effects: str = ""
    binding_rules: str = ""
    examples: list[str] = Field(default_factory=list)


class ItemQualitySystem(BaseModel):
    summary: str = ""
    grades: list[ItemGrade] = Field(default_factory=list)


RelationType = Literal["ally", "enemy", "neutral", "complex"]


class FactionRelation(BaseModel):
    target_id: str
    type: RelationType
    notes: str = ""


class FactionEntity(BaseModel):
    id: str
    name: str
    goals: str = ""
    territory: str = ""
    key_figures: list[str] = Field(default_factory=list)
    relations: list[FactionRelation] = Field(default_factory=list)


class FactionsSection(BaseModel):
    summary: str = ""
    entities: list[FactionEntity] = Field(default_factory=list)


class HistoryEvent(BaseModel):
    when: str = ""
    title: str = ""
    summary: str = ""
    consequences: list[str] = Field(default_factory=list)
    linked_faction_ids: list[str] = Field(default_factory=list)


class HistorySection(BaseModel):
    summary: str = ""
    events: list[HistoryEvent] = Field(default_factory=list)


class World(BaseModel):
    meta: Meta
    geography: GeographySection = Field(default_factory=GeographySection)
    power_system: PowerSystem = Field(default_factory=PowerSystem)
    item_quality_system: ItemQualitySystem = Field(default_factory=ItemQualitySystem)
    factions: FactionsSection = Field(default_factory=FactionsSection)
    history: HistorySection = Field(default_factory=HistorySection)

    def bump_version(self) -> None:
        self.meta.version = int(self.meta.version) + 1
        self.meta.updated_at = _utc_now_iso()
