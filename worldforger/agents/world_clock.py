# -*- coding: utf-8 -*-
"""WorldClock — time progression and external event injection.

Drives the narrative timeline forward and generates external events
that characters must respond to (mist surges, faction actions, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorldState:
    """Snapshot of world conditions at a point in time."""
    chapter: int = 0
    time_of_day: str = "上午"
    day: int = 1
    weather: str = "阴"
    mist_activity: str = "低"        # 低/中/高/狂暴
    season: str = "秋"


@dataclass
class WorldEvent:
    """An external event that characters cannot change, only respond to."""
    event_id: str = ""
    description: str = ""
    category: str = ""               # mist/faction/weather/discovery
    affected_locations: list[str] = field(default_factory=list)
    affected_characters: list[str] = field(default_factory=list)


class WorldClock:
    """Manages narrative time and generates external events.

    External events come from:
    1. The macro outline (parsed by OutlineConstraint)
    2. Faction-level actions (秦渊's orders, K's progress, etc.)
    3. Environmental changes (weather, mist surges, seasonal shifts)
    """

    # ── Faction-level event templates ──
    _FACTION_EVENTS = {
        "qinyuan_blockade": {
            "description": "秦渊的峡道封锁令进一步收紧——新增盘查关卡",
            "category": "faction",
            "affected_locations": ["南飞雁峡道", "北盘羊峡道"],
        },
        "k_node_activated": {
            "description": "K 激活了一座新的雕塑场节点——全球塑脉网络产生可感知的波动",
            "category": "mist",
            "affected_locations": ["千窟洞", "天枢广场"],
        },
        "iron_wall_patrol": {
            "description": "铁壁卫加强巡逻——峡道可见更多重装锻脉师",
            "category": "faction",
            "affected_locations": ["峡道全线"],
        },
        "mist_surge": {
            "description": "雾蚀边界突然扩张——最近澄明区边界后退数十米",
            "category": "mist",
        },
        "drift_soul_pulse": {
            "description": "漂魂岛雕塑发出异常脉冲——所有凝痕者都能感知到",
            "category": "mist",
            "affected_characters": ["all_凝痕者"],
        },
        "shanmu_ritual": {
            "description": "山母祭司在千窟洞举行仪式——地下塑脉网络活性上升",
            "category": "faction",
            "affected_locations": ["千窟洞", "乌龙半岛"],
        },
        "weather_storm": {
            "description": "暴风雨接近——海上航线中断，峡道能见度极低",
            "category": "weather",
        },
        "weather_fog": {
            "description": "浓雾降临——非雾蚀的普通浓雾，但能见度极差",
            "category": "weather",
        },
    }

    def __init__(self, state: WorldState | None = None):
        self.state = state or WorldState()

    def advance_chapter(self, chapter_num: int) -> list[WorldEvent]:
        """Advance to a new chapter, returning triggered external events."""
        self.state.chapter = chapter_num
        self.state.day += 1

        # Simple time-of-day cycling
        times = ["清晨", "上午", "中午", "下午", "黄昏", "夜间", "深夜"]
        self.state.time_of_day = times[chapter_num % len(times)]

        # Seasonal progression (every ~15 chapters = ~15 days)
        seasons = ["秋", "秋", "深秋", "冬", "冬", "冬", "早春", "春", "春", "夏", "夏", "夏"]
        self.state.season = seasons[min(chapter_num // 7, len(seasons) - 1)]

        return self._generate_events(chapter_num)

    def _generate_events(self, chapter_num: int) -> list[WorldEvent]:
        """Generate external events appropriate for this chapter."""
        events: list[WorldEvent] = []

        # Mist activity fluctuates
        if chapter_num % 5 == 0:
            self.state.mist_activity = "高"
            events.append(WorldEvent(
                event_id=f"evt_mist_{chapter_num}",
                description="雾蚀活跃度达到高峰——雕塑脉冲增强，凝痕态不稳定",
                category="mist",
            ))
        elif chapter_num % 3 == 0:
            self.state.mist_activity = "中"

        # Weather changes
        if chapter_num % 8 == 0:
            events.append(WorldEvent(
                event_id=f"evt_storm_{chapter_num}",
                description=self._FACTION_EVENTS["weather_storm"]["description"],
                category="weather",
            ))

        # Faction events based on story progression
        if 5 <= chapter_num <= 30:
            if chapter_num % 4 == 0:
                events.append(WorldEvent(
                    event_id=f"evt_blockade_{chapter_num}",
                    description=self._FACTION_EVENTS["qinyuan_blockade"]["description"],
                    category="faction",
                ))

        if chapter_num >= 15:
            if chapter_num % 7 == 0:
                events.append(WorldEvent(
                    event_id=f"evt_k_{chapter_num}",
                    description=self._FACTION_EVENTS["k_node_activated"]["description"],
                    category="mist",
                ))

        if chapter_num >= 20:
            if chapter_num % 6 == 0:
                events.append(WorldEvent(
                    event_id=f"evt_ritual_{chapter_num}",
                    description=self._FACTION_EVENTS["shanmu_ritual"]["description"],
                    category="faction",
                ))

        return events

    def scene_context_block(self) -> str:
        """Build a narrative context block describing current world state."""
        return (
            f"时间: 第{self.state.day}天 {self.state.time_of_day}，{self.state.season}季\n"
            f"天气: {self.state.weather} | 雾蚀活跃度: {self.state.mist_activity}"
        )
