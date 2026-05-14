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
请优先从叙事可用性出发：人物动机与秘密、冲突升级节奏、母题与象征、伏笔与回收点。
**地理（geography）**：**summary / climate_notes / map_notes** 分工总览与全图信息；可调用场景写入 **regions[]**——每区用 **summary** 与 **notes** 承载长叙事，**landmarks[]**、**resources[]** 只用短名；**relations** 写区与区之间的叙事/交通钩子（**target_id** 对齐对方 **id**）。避免纯百科堆砌。
**境界（power_system）**：**summary / realm_design_notes / skill_tree_design_notes** 与 **tiers[]** 分层叙事；**limitations** 写代价与禁忌；**skill_tree** 与 **subclass_paths** 的节点 **id**、**prereq_ids** 须可追踪；**profession_system** 与 **subclass_paths.profession_id** 对齐。勿与 **attribute_system**（人物强弱刻度）混写。
**物品（item_quality_system）**：**summary** 写宝物/道具在世界中的位置；**grades[]** 每档 **name**、**rarity_narrative**、**typical_effects**、**binding_rules**（谁可持、代价、易损毁点）；可选 **examples** 短例。叙事上的「物」与人物刻度分开写。
**生态（ecology）**：与 **geography**、**attribute_system** 对齐：**summary / design_notes**；**biomes[]**（**linked_region_ids** 对齐 **regions[].id**）；**species[]**（**biome_id**、**traits[]**、**notable_skills[]** 为物种层「技能/行为」短句，**非**境界 skill_tree 节点；**encounter_dialogue** 为遭遇台词/旁白）。
力量描写侧重「在故事里如何呈现、代价与反转」，少用数值堆砌。""",
    "game": """【当前载体：电子/桌游式游戏设定】
请优先从可玩性与可读规格出发：成长曲线、资源循环、职业或流派边界、关卡/区域与掉落或奖励的挂钩。
**地理（geography）**：**regions[]** 每项须有稳定 **id**（任务与同步引用）；**terrain / climate / notes** 便于关卡策划；**landmarks / resources** 短名列表绑定区域；**relations** 表达解锁顺序或邻接。**climate_notes / map_notes** 写全图规则。写成可做成任务链或区域解锁的模块。
**境界（power_system）**：**tiers[]** 写清 **typical_capabilities** 与 **limitations**（反作弊/硬边界）；**skill_tree**/**subclass_paths** 节点 id 稳定；**profession_id** 对齐 **profession_system.by_tier**；**realm_design_notes** 说明数值或规则在叙事上的映射。**物品**写入 **item_quality_system**（档位、**binding_rules**），与境界 **limitations** 分工明确。
**生态（ecology）**：**regions[].id** 绑定 **biomes[].linked_region_ids**；按 **attribute_system.stats** 的叙事强度设计危险生物与 **species.notable_skills**、**encounter_dialogue**。""",
    "coc": """【当前载体：克苏鲁的呼唤（CoC）跑团】
请优先调查与恐怖氛围：线索层级（表面线索/深入调查）、理智与压力源、神话接触的后果、当代或时代背景下的「日常崩坏」。
**地理（geography）**：**regions[]** 内用 **landmarks** 列可调查点、**resources** 列禁忌物或线索物（短名）；**notes** 写压力点与守秘人可用钩子；**summary** 写区域氛围与异常表层。**relations** 可表示调查轴或秘密传播路径（**target_id** 对齐区域 **id**）。派系写秘密教团、赞助者与不可知目标。
**境界（power_system）**：若有超自然力量，弱化「战力等级表」，强调仪式、知识污染、时间压力；**limitations** 写接触后果与守秘人可裁定边界；需要「卡面刻度」时写入 **attribute_system**，勿与境界技能树混谈。
**物品（item_quality_system）**：禁忌、副作用、调查用途写入 **rarity_narrative** / **typical_effects** / **binding_rules**；**grades[].name** 区分凡物/咒物等；**examples** 可列短例道具名。
**生态（ecology）**：怪异群落、民俗禁忌生物；**encounter_dialogue** 宜短、可朗读；**notable_skills** 写调查压力相关行为而非 PC 技能树。""",
    "dnd": """【当前载体：龙与地下城（D&D）类跑团】
请优先冒险与战斗可裁定性：生物/组织威胁层级、地形战术、派系任务与阵营钩子。
**地理（geography）**：**regions[]** 写 **terrain**、遭遇相关 **notes**、旅行节点式 **landmarks**；**relations** 写邻接/关隘/商路（**type** 短标签，**target_id** 对齐区域 **id**）。**climate_notes / map_notes** 服务旅行与随机遭遇裁定。历史写可触发冒险的「当前余波」。
**境界（power_system）**：**tiers[].limitations** 写明对 PC 的硬边界（可对照常见 tier，本地团自行换算）；**skill_tree**/**subclass_paths** 支持专长与遭遇；**profession_system** 与 **profession_id** 对齐。**物品（item_quality_system）**：**grades[]** 写稀有度叙事 **rarity_narrative**、效果 **typical_effects**、**binding_rules**（类 attunement / 交易限制）。
**生态（ecology）**：野外群落与随机遭遇；**biomes.linked_region_ids** 对齐 **regions[].id**；**species.notable_skills** 便于动作裁定；**encounter_dialogue** 供 DM 朗读。""",
}


# --- 结构化同步：附加在 STRUCTURE_SYSTEM 后，引导写入 world.json 的侧重点 ---

STRUCTURE_SYNC_ADDON: dict[str, str] = {
    "novel": """【载体：小说】若抽取可落盘内容，优先写入能服务叙事的信息：history.events 写清后果与可挂钩派系；factions.entities 写目标、地盘与人物线索；cultures.entities 写观念冲突、仪式与禁忌如何驱动人物选择；**geography**：summary 写宏观总览，**regions[]** 写可调用场景（每区 **summary / notes / landmarks / resources** 分工：长叙事进 summary 或 notes，地标与物产用短名列表）；**ecology**：**summary / design_notes**；**biomes[]**（**id**、**name**、**linked_region_ids[]** 须对齐已有 **regions[].id**）；**species[]**（**biome_id** 对齐 **biomes[].id**；**traits[]**、**notable_skills[]** 为物种行为/生态位短句，**encounter_dialogue** 为遭遇台词或环境旁白）；**power_system**：**summary / realm_design_notes / skill_tree_design_notes** 与 **tiers[]**（**limitations** 写代价与禁忌）；**skill_tree**/**subclass_paths** 节点 **id** 稳定、**prereq_ids** 只引用同树；**profession_system** 与 **profession_id** 对齐；**item_quality_system**：**summary** + **grades[]**（每档 **name**、**rarity_narrative**、**typical_effects**、**binding_rules**、可选 **examples**），叙事代价与意象落在档位叙事与规则中。**若讨论人物强弱刻度、六维/雷达式评判或建卡属性，须输出 attribute_system（summary、design_notes、stats 含 intro、可选 tier_average_profiles 与各境 averages），与 power_system 境界区分。若讨论主角团、配角或人物关系，须输出 **characters**（**summary**、**design_notes**、**entities[]** 含 **cast_role**/**faction_ids[]**/**home_region_id**/**notable_skills[]**、**relations[]** 含 **source_id**/**target_id**/**relation_type**）。**""",
    "game": """【载体：游戏】若抽取可落盘内容，优先写入可策划落地的信息：**power_system.tiers** 写清 **typical_capabilities** 与 **limitations**；每境 **skill_tree**、**subclass_paths** 与 **profession_system.by_tier**（**profession_id** 与职业 **id** 一致）；**realm_design_notes**/**skill_tree_design_notes** 写规则边界；**item_quality_system**：**summary** + **grades[]**（**name**、**rarity_narrative**、**typical_effects**、**binding_rules**、可选 **examples**），档位与掉落/交易/绑定玩法挂钩；**attribute_system** 写 stats 与 design_notes 便于建卡与 UI；**geography.regions[]** 绑定关卡/掉落/声望（**id** 稳定以便 relations）；**ecology** 写区域生态位、游荡怪/资源生物、**species.notable_skills** 便于技能化遭遇；**characters** 写卡司 **entities[]**/**relations[]**（阵营/区域 id 须对齐）；factions、cultures、history 同上。""",
    "coc": """【载体：CoC】若抽取可落盘内容，优先调查链：**geography.regions[]** 写可调查地点（**landmarks**）、禁忌资源（**resources**）、**notes** 藏线索层级；勿把长调查说明只塞进列表项；factions 写教团层级、掩护身份与神话线索；cultures 写民间禁忌、密教变体、理智压力源与「正常社会下的异常」；history.events 写年代与「被掩盖的真相」；**ecology** 写不可名状生态位、民俗禁忌与**encounter_dialogue**（压力台词）；**item_quality_system**：禁忌、副作用、调查链写入 **grades** 的 **rarity_narrative** / **typical_effects** / **binding_rules**；**power_system** 若有则强调仪式/知识代价，**limitations** 写接触后果；**skill_tree** 节点 id 清晰。**characters** 写调查员/NPC 卡司与人物关系边（**relations**）。**调查员或 NPC 的可检定属性、理智/压力相关维度或「人物卡」尺度，须写入 attribute_system（stats + design_notes），勿与境界技能树混为一谈时可分条说明。**""",
    "dnd": """【载体：D&D】若抽取可落盘内容，优先冒险裁定：**geography.regions[]** 写 encounter 地形、旅行节点（**terrain / notes / relations**）；factions 写据点、任务发布者与阵营；cultures 写神殿网络、节日、阵营意识形态与可扮演钩子；**ecology** 写野外生物群落、**species.notable_skills**（动作/反应式行为）与 **encounter_dialogue**（DM 可读旁白）；**power_system**：**tiers[].limitations** 写对 PC 硬边界；**skill_tree**/**subclass_paths** 服务遭遇与专长；**profession_system** 与 **profession_id** 对齐；**attribute_system** 可对齐六维或自定义检定向属性；**item_quality_system**：**grades[]** 写 **rarity_narrative**、**typical_effects**、**binding_rules**（稀有度与绑定/交易规则）；**characters** 写 PC/NPC 卡司与关系网；history 写当前冒险钩子。""",
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


# --- 对话：可选「技能引导」片段（由前端 chat_guides 勾选，追加为 system）---

ALLOWED_CHAT_GUIDES = frozenset(
    {"skill_trees", "profession_system", "attribute_system", "ecology", "economy", "character_roster"}
)

CHAT_GUIDE_FRAGMENTS: dict[str, str] = {
    "skill_trees": """【本对话附加任务：境界体系与技能树】
请在适当时用可写入 world.json 的 **power_system** 结构讨论（顶层键必须为 **power_system**，勿拆到根级）：
- **境界总览**：**summary**；**realm_design_notes**（递进、命名、破境代价、与 **attribute_system** 的边界）；**skill_tree_design_notes**（跨境节点 **id** 规则、**prereq_ids** 含义、通用 **skill_tree** 与子类 **subclass_paths** 专属树如何并存）。
- **tiers[]**：每境 **name**、**description**、**typical_capabilities[]**、**limitations[]**、**examples[]**；**limitations** 宜写可裁定代价或禁忌。
- **skill_tree**（每境可选）：节点含 **id**（该境该树内唯一）、**name**、**summary**、**prereq_ids**（仅引用**本树**已出现 **id**）、**branch**（可选）。
- **subclass_paths**（每境可选）：**id**、**name**、**tagline**、**flavor**；**profession_id** 须与同境 **profession_system.by_tier** 中对应 **professions[].id** 一致；可含专属 **skill_tree**（节点 **id** 建议加前缀以免与境界通用树冲突）。
- 说明通用节点与子类分叉的关系（共享底层、分叉高层、互斥专精等）。""",
    "profession_system": """【本对话附加任务：境界职业体系】
请帮助用户设计 **power_system.profession_system**（与 **attribute_system** 独立；与 **subclass_paths.profession_id** 可互相引用）：
- **summary**：职业/流派在世界中的定位（宗门、军团、秘传、公会体系等）。
- **design_notes**：各境职业如何递进、与派系/文化/资源的关系；**exclusive_faction_id** 何时使用（须为已有 **factions.entities[].id**）。
- **by_tier[]**：与 **power_system.tiers** 顺序或 **tier_name** 对齐；每项 **professions[]** 含 **id**（短 id、在**单境内**唯一）、**name**、**tagline**、**flavor**、**exclusive_faction_id**（可选）、**notes**。
- 若已讨论技能树：各 **subclass_paths** 的 **profession_id** 必须绑定到上述**同境**某职业 **id**，避免同名不同义。
结构化同步落盘时写入 **power_system.profession_system**（与 **tiers** 同对象合并）；优先不要单独使用顶层键 **profession_system**（后端可归并，但易歧义）。""",
    "attribute_system": """【本对话附加任务：通用人物属性】
请帮助用户设计 **attribute_system**（与境界体系 power_system 独立，用于「人物有多强/擅长什么」的通用评判）：
- **summary**：这套属性在世界中的定位（小说叙事向 / 跑团检定 / 游戏数值的叙事映射等）。
- **design_notes**：如何读雷达图、建卡建议、与当前创作载体尺度对齐方式。
- **stats[]**：每项 **id**、**name**、**abbreviation**、**intro**（该维度单独一句话简介，便于看板展示）、**description**（可较长）、**scale**、**typical_use**、**reference_percent**（0–100，雷达上世界参照强度）。
- **tier_average_profiles[]**（可选）：与 **power_system.tiers** 各境名称对齐，每项 **tier_name** + **averages**（键为 stat **id**、值 0–100）。前端雷达：**缺键的轴为 0**；若 averages 与当前 stats 的 id 无一能对齐则**不画该境**。
维度数量建议 4–8 个，命名互不重叠。
**对话后「结构化同步」落盘时，JSON 顶层键必须写 attribute_system**（勿用 attributes、character_stats 等别名；stats 每项务必有 id 与 name）。
**创作模式**：选 **DnD / CoC** 时可采用接近官方卡面的固定维度（如六维、理智等）；选 **小说 / 游戏** 时请按世界观自定义 stats 名称与数量。""",
    "ecology": """【本对话附加任务：生态与生物群落】
请结合当前 **geography**（尤其 **regions[].id**、气候/地貌/notes）与 **attribute_system.stats**（各维度叙事刻度）推演 **ecology**（顶层键必须为 **ecology**）：
- **summary**：全图食物网、危险带、与文明/魔法的交界如何塑造野外。
- **design_notes**：生境与人物属性雷达如何互证（例如高威胁区对应哪些 stat 叙事）。
- **biomes[]**：每项 **id**、**name**、**summary**；**linked_region_ids[]** 引用已有 **geography.regions[].id**；可选 **climate_habitat**、**hazards**、**notes**。
- **species[]**：每项 **id**、**name**、**biome_id**（须为本次或已有 **biomes[].id**）；**traits[]**（生态位/标签短名）；**notable_skills[]**（物种层行为或「类技能」短句，**不是**境界 **skill_tree** 节点）；**encounter_dialogue**（一句遭遇台词、环境旁白或守秘人/DM 可读提示）；可选 **danger_notes**、**ecology_notes**。
对话后「结构化同步」落盘时顶层键写 **ecology**；与助手讨论时可用小节标题组织，便于第二路抽取。""",
    "economy": """【本对话附加任务：经济与流通 economy】
请结合当前 **geography.regions**、**factions.entities**、**item_quality_system**（若已有）设计可落盘的 **economy**（顶层键必须为 **economy**）：
- **summary** / **design_notes**：通货与流通总览；铸币权、商会、关税与 **regions[].id**、**factions.entities[].id** 的对齐说明。
- **currencies[]**：**id**、**name**；可选 **symbol**、**issuer_faction_id**（须为已有派系 **id**）、**exchange_notes**。
- **markets[]**：**id**、**name**；可选 **summary**、**linked_region_ids[]**、**dominant_faction_ids[]**、**notes**。
- **trade_routes[]**：**id**、**name**、**from_region_id**、**to_region_id**（须为已有区域 **id**）；可选 **summary**、**goods_notes**、**controlling_faction_ids[]**、**notes**。
- **trade_goods[]**：**id**、**name**；可选 **category**（如 strategic|luxury|common|contraband）、**summary**、**notes**。
- **labor_notes**、**taxation_notes**、**volatility_notes**：劳动力/税收再分配/危机与物价波动等。
对话后「结构化同步」落盘时顶层键写 **economy**；勿编造不存在的区域或派系 **id**。""",
    "character_roster": """【本对话附加任务：人物卡司 characters】
请结合当前 **factions**、**cultures**、**history**、**geography.regions** 设计可落盘的 **characters**（顶层键必须为 **characters**）：
- **summary** / **design_notes**：卡司总览、与派系要人/历史事件/籍贯区域的对齐说明。
- **entities[]**：每项 **id**、**name**；**cast_role** 取 `protagonist_core`（主角团核心）| `supporting_major`（重要配角）| `supporting_minor` | `antagonist` | `background`；**faction_ids[]** 对齐 **factions.entities[].id**；**home_region_id** 对齐 **geography.regions[].id**；**one_line_hook**；**notes**；**notable_skills[]**（人物叙事或玩法向特长短句，**非**境界 **power_system.skill_tree** 节点）。
- **relations[]**：**source_id**、**target_id** 均为 **entities[].id**；**relation_type**（如 ally/rival/family/debt/secret）；可选 **visibility**（reader/author_only）、**notes**。
对话后「结构化同步」落盘时顶层键写 **characters**。""",
}


def chat_guides_content(guides: list[str] | None) -> str | None:
    """将前端传入的 chat_guides 转为一段可拼进对话的 system 文本。"""
    if not guides:
        return None
    parts = [CHAT_GUIDE_FRAGMENTS[g] for g in guides if g in CHAT_GUIDE_FRAGMENTS]
    if not parts:
        return None
    return "\n\n".join(parts)


def normalize_chat_guides(raw: object) -> list[str]:
    """仅保留白名单内的引导 id。"""
    if not raw or not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip() in ALLOWED_CHAT_GUIDES]


def genre_tags_prompt_addon(tags: list[str] | None) -> str | None:
    """将 meta.genre_tags 拼成一段 system 补充，供对话 / 同步 / 大纲复用。"""
    arr = [str(t).strip() for t in (tags or []) if str(t).strip()]
    if not arr:
        return None
    joined = "、".join(arr[:24])
    tail = "…" if len(arr) > 24 else ""
    return (
        "【创作题材标签（meta.genre_tags）】用户为本书/世界标注："
        + joined
        + tail
        + "。请在语气、案例与可落盘设定上贴合这些题材与氛围；若标签抽象，可作合理具象展开，且须与 world.json 其它事实不自相矛盾。"
    )
