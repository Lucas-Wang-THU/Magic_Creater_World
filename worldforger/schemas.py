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
    """地理：总览在 summary；大陆/王国等可区分单元在 regions[]。

    每个 region 建议含 id、name、summary；可选 terrain、climate、notes、
    landmarks[]、resources[]、relations[]（target_id/type/notes）。
    顶层 landmarks/resources 为可选汇总或与旧档兼容，结构化同步优先写入各区域。
    """

    summary: str = ""
    regions: list[dict[str, Any]] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    climate_notes: str = ""
    resources: list[str] = Field(default_factory=list)
    map_notes: str = ""


class SkillNode(BaseModel):
    """技能树节点：用于境界通用树或子类职业专属树。"""

    id: str
    name: str
    summary: str = ""
    prereq_ids: list[str] = Field(default_factory=list)
    branch: str = ""


class SubclassPath(BaseModel):
    """同一境界下的子类职业（流派），带独立技能树。"""

    id: str
    name: str
    tagline: str = ""
    flavor: str = ""
    skill_tree: list[SkillNode] = Field(default_factory=list)
    profession_id: str = Field(
        default="",
        description="可选：与 power_system.profession_system 中本境对应条目的 ProfessionEntry.id 对齐，便于技能树流派引用职业设定。",
    )


class ProfessionEntry(BaseModel):
    """某一境界下的职业/流派定位（叙事与规则）；技能树 subclass_paths 可通过 profession_id 引用。"""

    id: str
    name: str
    tagline: str = ""
    flavor: str = ""
    exclusive_faction_id: str = Field(
        default="",
        description="若非空，表示该职业主要由该派系掌握、垄断或秘传；对应 factions.entities[].id。",
    )
    notes: str = ""


class TierProfessionBlock(BaseModel):
    """与 power_system.tiers 顺序对齐为佳：第 i 项对应第 i 个境界。"""

    tier_name: str = ""
    professions: list[ProfessionEntry] = Field(default_factory=list)


class ProfessionSystem(BaseModel):
    summary: str = ""
    design_notes: str = ""
    by_tier: list[TierProfessionBlock] = Field(
        default_factory=list,
        description="按境界分组的职业表；与 tiers[] 一一对应时 tier_name 建议与 tiers[i].name 一致。",
    )


class PowerTier(BaseModel):
    name: str
    description: str = ""
    typical_capabilities: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    skill_tree: list[SkillNode] = Field(
        default_factory=list,
        description="本境界通用技能树（与 subclass_paths 中树并存；节点 id 建议带境界前缀以免冲突）。",
    )
    subclass_paths: list[SubclassPath] = Field(
        default_factory=list,
        description="子类职业：每条有独立 skill_tree，体现流派差异。",
    )


class PowerSystem(BaseModel):
    summary: str = ""
    realm_design_notes: str = Field(
        default="",
        description="境界概述的设计说明：递进逻辑、命名规则、与叙事或其它力量体系的边界等。",
    )
    skill_tree_design_notes: str = Field(
        default="",
        description="境界技能树的设计说明：跨境界的节点命名、前置含义、通用树与子类流派树的关系等。",
    )
    profession_system: ProfessionSystem = Field(
        default_factory=ProfessionSystem,
        description="按境界划分的职业/流派体系；技能树 subclass_paths 可用 profession_id 引用其中条目。",
    )
    tiers: list[PowerTier] = Field(default_factory=list)


class AttributeStat(BaseModel):
    """通用人物属性维度（叙事或规则向均可）。"""

    id: str
    name: str
    abbreviation: str = ""
    intro: str = Field(
        default="",
        description="该维度单独简介（一句话或短段），用于看板展示与雷达旁提示；与 description 长说明区分。",
    )
    description: str = ""
    scale: str = ""
    typical_use: str = ""
    reference_percent: int = Field(
        default=55,
        ge=0,
        le=100,
        description="看板雷达上该维度的参照强度（世界常态/英雄基准等），0–100。",
    )
    radar_icon: str = Field(
        default="",
        description="雷达轴端 Material Symbols 图标名（ligature，如 fitness_center）；空则按 id/name 启发式匹配。",
    )


class TierAttributeAverage(BaseModel):
    """某一境界在通用人物属性各维度上的「普通人物」平均刻度，与 stats[].id 对齐。"""

    tier_name: str = Field(
        default="",
        description="建议与 power_system.tiers[].name 一致，便于读者对照境界表。",
    )
    averages: dict[str, int] = Field(
        default_factory=dict,
        description="stat id → 0–100；前端雷达上缺键的轴按 0；与 stats.id 无一能对齐则不绘制该境。",
    )

    @field_validator("averages", mode="before")
    @classmethod
    def _clamp_averages(cls, v: object) -> dict[str, int]:
        if not isinstance(v, dict):
            return {}
        out: dict[str, int] = {}
        for k, raw in v.items():
            key = str(k).strip()
            if not key:
                continue
            try:
                n = int(round(float(raw)))
            except (TypeError, ValueError):
                continue
            out[key] = max(0, min(100, n))
        return out


class AttributeSystem(BaseModel):
    summary: str = ""
    design_notes: str = ""
    stats: list[AttributeStat] = Field(default_factory=list)
    tier_average_profiles: list[TierAttributeAverage] = Field(
        default_factory=list,
        description="各境界在本属性体系下的平均人物雷达；与 power_system 各境名称对应为佳。",
    )


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


class EconomySection(BaseModel):
    """经济与流通：货币、市场、商路与贸易品；引用 geography.regions、factions.entities 的 id。"""

    summary: str = ""
    design_notes: str = ""
    currencies: list[dict[str, Any]] = Field(
        default_factory=list,
        description="货币或等价物：id、name；可选 symbol、issuer_faction_id、exchange_notes。",
    )
    markets: list[dict[str, Any]] = Field(
        default_factory=list,
        description="市场层级：id、name；可选 summary、linked_region_ids[]、dominant_faction_ids[]、notes。",
    )
    trade_routes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="商路：id、name、from_region_id、to_region_id；可选 summary、goods_notes、controlling_faction_ids[]、notes。",
    )
    trade_goods: list[dict[str, Any]] = Field(
        default_factory=list,
        description="战略/奢侈/违禁等：id、name；可选 category、summary、notes。",
    )
    labor_notes: str = ""
    taxation_notes: str = ""
    volatility_notes: str = ""


CultureKind = Literal["culture", "religion", "syncretic"]


class CultureRelation(BaseModel):
    target_id: str
    type: str = "influence"
    notes: str = ""


class CultureEntity(BaseModel):
    id: str
    name: str
    kind: CultureKind = "culture"
    summary: str = ""
    tenets: str = ""
    practices: str = ""
    sacred_sites: list[str] = Field(default_factory=list)
    key_figures: list[str] = Field(default_factory=list)
    relations: list[CultureRelation] = Field(default_factory=list)


class CulturesSection(BaseModel):
    summary: str = ""
    entities: list[CultureEntity] = Field(default_factory=list)


class CharactersSection(BaseModel):
    """人物卡司：与派系、地理、历史对齐；entities 为角色条目，relations 为角色间有向边。"""

    summary: str = ""
    design_notes: str = ""
    entities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="每项建议 id、name、aliases[]、cast_role（protagonist_core|supporting_major|supporting_minor|antagonist|background）、"
        "faction_ids[]（factions.entities[].id）、home_region_id（geography.regions[].id）、one_line_hook、notes、notable_skills[]（叙事向人物特长/技能短句，非境界 skill_tree）。",
    )
    relations: list[dict[str, Any]] = Field(
        default_factory=list,
        description="人物关系边：source_id、target_id（均为 characters.entities[].id）、relation_type（如 ally/rival/family/debt/secret）、"
        "visibility（如 reader|author_only）、notes。",
    )


class EcologySection(BaseModel):
    """生态：依地理与人物属性维度推演生境、物种与遭遇话术（与 geography / attribute_system 对齐引用）。"""

    summary: str = ""
    design_notes: str = ""
    biomes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="生境群落：每项建议 id、name、summary、linked_region_ids[]（geography.regions[].id）、climate_habitat 等。",
    )
    species: list[dict[str, Any]] = Field(
        default_factory=list,
        description="代表性物种或群落：每项建议 id、name、biome_id、traits[]、notable_skills[]（叙事或规则向技能/行为）、encounter_dialogue（遭遇台词/环境旁白）、danger_notes。",
    )


StoryPerson = Literal["first_person", "third_person_limited", "third_person_omniscient"]
StoryChapterStatus = Literal["planned", "drafting", "locked"]
StoryForeshadowStatus = Literal["open", "partial", "resolved"]


class ChapterSummaryCard(BaseModel):
    """章节收尾自动摘要——用于下一章上下文注入，替代原文截断。"""

    chapter_id: str = ""
    title: str = ""
    main_events: str = Field(default="", description="本章主要事件概述（200 字以内）")
    character_state_changes: list[dict[str, str]] = Field(
        default_factory=list,
        description="各角色状态变化：{char_id, name, location_before, location_after, "
        "emotion_before, emotion_after, new_items, goal_change}",
    )
    foreshadowing_planted: list[str] = Field(default_factory=list, description="本章新埋设的伏笔 id 列表")
    foreshadowing_resolved: list[str] = Field(default_factory=list, description="本章回收的伏笔 id 列表")
    ending_hook: str = Field(default="", description="结尾钩子（本章结束时未解决的悬念，下一章需承接）")


class CharacterRuntimeState(BaseModel):
    """角色运行时状态——追踪角色在叙事中的当前位置、情绪、目标等动态信息。"""

    current_location: str = Field(default="", description="角色当前所在地点")
    current_goal: str = Field(default="", description="角色当前目标")
    emotional_state: str = Field(default="", description="角色当前情绪状态")
    inventory_changes: list[str] = Field(default_factory=list, description="最近获得的物品/能力")
    relationship_updates: dict[str, str] = Field(
        default_factory=dict, description="与其他角色的关系变化：char_id → 变化描述"
    )
    last_updated_chapter: str = Field(default="", description="最后更新此状态的章节 id")


class StoryNarrator(BaseModel):
    character_id: str = Field(default="", description="对齐 characters.entities[].id，空表示不绑定 POV 角色。")
    person: StoryPerson = "third_person_limited"
    voice_notes: str = ""


class StoryWritingDefaults(BaseModel):
    attach_prev_chapters: int = Field(default=3, ge=0, le=5)
    include_world_md: bool = False
    include_macro_outline: bool = True
    include_chapter_beats: bool = True


class StoryOutlineMacro(BaseModel):
    file: str = "story/macro_outline.md"
    updated_at: str = ""


class StoryChapter(BaseModel):
    id: str
    order: int = 1
    title: str = ""
    status: StoryChapterStatus = "planned"
    beat_file: str = ""
    manuscript_file: str = ""
    word_count: int = 0
    reader_synopsis: str = ""
    author_notes: str = ""
    summary_card: ChapterSummaryCard | None = Field(default=None, description="本章收尾摘要卡片")


class StoryForeshadowing(BaseModel):
    id: str
    label: str = ""
    planted_chapter_id: str = ""
    payoff_chapter_id: str = ""
    reader_known: bool = False
    status: StoryForeshadowStatus = "open"
    notes: str = ""


class StorySection(BaseModel):
    """情节：粗纲/细纲/文稿索引；正文存 worlds/<id>/story/ 下 Markdown 文件。"""

    summary: str = ""
    design_notes: str = ""
    unit_label: str = Field(
        default="",
        description="章/章节/跑团会话等；空时由 meta.creative_mode 推导。",
    )
    target_units: int | None = None
    narrator: StoryNarrator = Field(default_factory=StoryNarrator)
    writing_defaults: StoryWritingDefaults = Field(default_factory=StoryWritingDefaults)
    outline_macro: StoryOutlineMacro = Field(default_factory=StoryOutlineMacro)
    chapters: list[StoryChapter] = Field(default_factory=list)
    foreshadowing: list[StoryForeshadowing] = Field(default_factory=list)


class World(BaseModel):
    meta: Meta
    geography: GeographySection = Field(default_factory=GeographySection)
    ecology: EcologySection = Field(default_factory=EcologySection)
    power_system: PowerSystem = Field(default_factory=PowerSystem)
    item_quality_system: ItemQualitySystem = Field(default_factory=ItemQualitySystem)
    attribute_system: AttributeSystem = Field(default_factory=AttributeSystem)
    factions: FactionsSection = Field(default_factory=FactionsSection)
    cultures: CulturesSection = Field(default_factory=CulturesSection)
    characters: CharactersSection = Field(default_factory=CharactersSection)
    history: HistorySection = Field(default_factory=HistorySection)
    economy: EconomySection = Field(default_factory=EconomySection)
    story: StorySection = Field(default_factory=StorySection)

    def bump_version(self) -> None:
        self.meta.version = int(self.meta.version) + 1
        self.meta.updated_at = _utc_now_iso()
