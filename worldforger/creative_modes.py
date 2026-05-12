"""创作载体（小说 / 游戏 / CoC / DnD）对应的提示侧重，供对话、大纲与结构化同步复用。"""

from __future__ import annotations

ALLOWED_CREATIVE_MODES = frozenset({"novel", "game", "coc", "dnd"})


def normalize_creative_mode(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    k = str(raw).strip().lower()
    return k if k in ALLOWED_CREATIVE_MODES else None


# --- 对话：追加在 world JSON 系统提示之后（独立 system 条或拼接）---

CHAT_MODE_SYSTEM: dict[str, str] = {
    "novel": """【当前载体：长篇小说】
请优先从叙事可用性出发：人物动机与秘密、冲突升级节奏、母题与象征、伏笔与回收点；地理与派系写「可被情节调用」的细节（场景、道具、势力边界），避免纯百科堆砌。
力量与物品描写侧重「在故事里如何呈现、代价与反转」，少用数值堆砌。""",
    "game": """【当前载体：电子/桌游式游戏设定】
请优先从可玩性与可读规格出发：成长曲线、资源循环、职业或流派边界、关卡/区域与掉落或奖励的挂钩；地理与历史写成「可做成任务链或区域解锁」的模块。
力量体系与物品档位需便于策划落地（层级清晰、边界规则、反作弊/平衡约束可写在 limitations / binding_rules）。""",
    "coc": """【当前载体：克苏鲁的呼唤（CoC）跑团】
请优先调查与恐怖氛围：线索层级（表面线索/深入调查）、理智与压力源、神话接触的后果、当代或时代背景下的「日常崩坏」；地理写可调查地点与隐藏关联；派系写秘密教团、赞助者与不可知目标。
力量体系若存在超自然，应弱化「战斗等级」，强调仪式代价、知识污染与时间压力；物品写禁忌、副作用与调查用途。""",
    "dnd": """【当前载体：龙与地下城（D&D）类跑团】
请优先冒险与战斗可裁定性：生物/组织威胁层级、地形战术、派系任务与阵营钩子；地理写 encounter 地形与旅行节点；历史写可触发冒险的「当前余波」。
力量体系可对照常见 tier（本地团自行换算），在 tiers 的 limitations 中写明对 PC 的硬边界；物品写稀有度叙事与 attunement 式绑定规则（用 binding_rules 表达）。""",
}


# --- 结构化同步：附加在 STRUCTURE_SYSTEM 后，引导写入 world.json 的侧重点 ---

STRUCTURE_SYNC_ADDON: dict[str, str] = {
    "novel": """【载体：小说】若抽取可落盘内容，优先写入能服务叙事的信息：history.events 写清后果与可挂钩派系；factions.entities 写目标、地盘与人物线索；cultures.entities 写观念冲突、仪式与禁忌如何驱动人物选择；geography.regions 写可被场景调用的地貌与氛围；物品与力量写「叙事代价与意象」。""",
    "game": """【载体：游戏】若抽取可落盘内容，优先写入可策划落地的信息：power_system.tiers 与 item_quality_system.grades 写清边界与典型玩法；geography 与 factions 写任务/区域控制与奖励链可挂钩点；cultures 写阵营 Buff、声望、节日活动或派系意识形态标签；history 可写版本事件或世界状态变更。""",
    "coc": """【载体：CoC】若抽取可落盘内容，优先调查链：geography / landmarks / regions 写可调查点与隐藏关联；factions 写教团层级、掩护身份与神话线索；cultures 写民间禁忌、密教变体、理智压力源与「正常社会下的异常」；history.events 写年代与「被掩盖的真相」；物品写禁忌与副作用；力量体系若有则强调仪式/知识代价而非战力数值。""",
    "dnd": """【载体：D&D】若抽取可落盘内容，优先冒险裁定：geography 写旅行危险与地标遭遇；factions 写据点、任务发布者与阵营；cultures 写神殿网络、节日、阵营意识形态与可扮演钩子；power_system 写清晰层级与对 PC 的硬限制；items 写稀有度与绑定/使用规则；history 写当前仍在发生的冒险钩子。""",
}


# --- 大纲：附加在 outline 系统提示末尾 ---

OUTLINE_MODE_ADDON: dict[str, str] = {
    "novel": "输出时标明人物弧线与伏笔位；情节总纲分幕并标出张力峰值。",
    "game": "输出时区分主线/支线与可选分支；标注可映射为任务或系统的节点。",
    "coc": "输出时标注线索层级、理智/压力风险点、守密人可藏的反转；人物小传含秘密与弱点。",
    "dnd": "输出时标注建议等级区间或威胁感、阵营与任务钩子；人物小传含种族职业背景与冒险动机。",
}


def chat_mode_system(mode: str | None) -> str | None:
    m = normalize_creative_mode(mode)
    return CHAT_MODE_SYSTEM.get(m) if m else None


def structure_sync_addon(mode: str | None) -> str:
    m = normalize_creative_mode(mode)
    if not m:
        return ""
    return "\n" + STRUCTURE_SYNC_ADDON.get(m, "")


def outline_mode_addon(mode: str | None) -> str:
    m = normalize_creative_mode(mode)
    if not m:
        return ""
    return OUTLINE_MODE_ADDON.get(m, "")
