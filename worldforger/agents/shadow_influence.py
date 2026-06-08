# -*- coding: utf-8 -*-
"""Shadow influence — convert off-screen character actions into
environmental details the POV character may notice."""

from __future__ import annotations

from worldforger.agents.types import AgentDecision, AgentSimResult, CharacterAgentState


class ShadowInfluence:
    """Convert off-screen actions to environmental hints for the POV character.

    When a character acts off-screen, their actions may leave traces
    the POV character notices later:
    - A locked door that was previously open
    - Fresh footprints
    - Distant sounds or signals
    - An NPC mentioning something unusual
    - Plastic vein network fluctuations
    """

    # Mapping: shadow action keywords → environmental hint templates
    _HINT_TEMPLATES = [
        (("审讯", "审问", "拷问"), "{name}正在某处被审讯——远处的哨站灯火通明至深夜"),
        (("追踪", "跟踪", "追踪"), "峡道石壁上出现了新鲜的标记——{name}或许来过"),
        (("封锁", "设卡", "盘查"), "前方道路上有新设的路障——{name}的封锁令正在执行"),
        (("激活", "雕塑", "节点"), "远处雕塑场方向传来微弱的低频脉冲——{name}推进了图谱"),
        (("仪式", "祈祷", "祭祀"), "空气中飘着焚烧过的草药气味——{name}可能刚完成仪式"),
        (("移动", "前进", "赶往"), "路面有新踩过的痕迹——{name}不久前经过此处"),
        (("信号", "传讯", "通讯"), "峡道上空短暂出现了军用信号弹的残光——{name}在发出信号"),
        (("搜索", "搜查", "寻找"), "路边几个背包被翻过——{name}在搜索什么东西"),
    ]

    @staticmethod
    def generate_hints(shadow_events: list[str]) -> list[str]:
        """Generate environmental hints from off-screen character actions."""
        hints: list[str] = []
        for shadow in shadow_events:
            if ":" not in shadow:
                continue
            name, action = shadow.split(":", 1)
            name = name.strip()
            action = action.strip()

            for keywords, template in ShadowInfluence._HINT_TEMPLATES:
                if any(kw in action for kw in keywords):
                    hint = template.format(name=name)
                    hints.append(f"[环境线索] {hint}")
                    break
            else:
                # Generic fallback
                if action:
                    hints.append(f"[环境线索] 远处有异常迹象——可能与{name}的动向有关")

        return hints

    @staticmethod
    def link_to_foreshadowing(
        hints: list[str],
        foreshadowing_ledger: list,
    ) -> list[dict]:
        """Check if any shadow hints connect to existing foreshadowing.

        Returns list of {hint, foreshadowing_id, foreshadowing_label} matches.
        """
        links = []
        for hint in hints:
            for fs in foreshadowing_ledger:
                # Access both Pydantic model and dict style
                label = getattr(fs, "label", "") if hasattr(fs, "label") else fs.get("label", "")
                notes = getattr(fs, "notes", "") if hasattr(fs, "notes") else fs.get("notes", "")
                fs_id = getattr(fs, "id", "") if hasattr(fs, "id") else fs.get("id", "")

                if label and any(kw in hint for kw in (label, notes)):
                    links.append({
                        "hint": hint,
                        "foreshadowing_id": fs_id,
                        "foreshadowing_label": label,
                        "suggestion": f"读者可能记得伏笔'{label}'——可在环境描写中给隐晦暗示",
                    })
                    break
        return links

    @staticmethod
    def format_shadow_context(
        shadow_events: list[str],
        hints: list[str],
        fs_links: list[dict],
    ) -> str:
        """Build a writer-agent prompt block for shadow influences."""
        parts: list[str] = []
        if hints:
            parts.append("【幕后角色的环境痕迹（POV 角色可能察觉的线索）】")
            for h in hints[:5]:
                parts.append(f"  {h}")
        if fs_links:
            parts.append("\n【伏笔关联（可在环境描写中暗示，不可明写）】")
            for link in fs_links[:3]:
                parts.append(f"  - 伏笔'{link['foreshadowing_label']}': {link['suggestion']}")
        return "\n".join(parts)
