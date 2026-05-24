# Magic Creater World — 文学呼吸感：从"成立的故事"到"活着的人"

> 诊断日期：2026-05-24
> 核心判断：世界构建和剧情结构已基本完善，当前最大问题是 **"小说的呼吸感不够"**——它已经像一个成熟故事，但还不像"真正活着的人"。
>
> 以下方案从 Agent 系统角度，将十大文学性诊断转化为可落地的功能模块。

---

## 总览

```
                    ┌──────────────────────────────────────┐
                    │        文学呼吸感 十大模块           │
                    └──────────────────────────────────────┘
                                        │
            ┌───────────────────────────┼───────────────────────────┐
            │ P0（即刻可做）            │ P1（需一定设计）           │ P2（长期深耕）    │
            │ 主要改 prompt + schema    │ 新增生成模式 + 检测器       │ 深度追踪系统      │
            ├───────────────────────────┼───────────────────────────┼──────────────────┤
            │ 1. 角色语言风格档案       │ 4. 呼吸段落生成模式        │ 8. 设定揭示度追踪 │
            │ 2. 情绪后遗症追踪器       │ 5. 金句密度控制器          │ 9. 不可逆失败系统 │
            │ 3. 反「成长公式」提示词   │ 6. 人性缺陷与关系伤害      │ 10. 角色相互改变  │
            │                           │ 7. 微观习惯/小尺度情感库   │                   │
            └───────────────────────────┴───────────────────────────┴──────────────────┘
```

---

## 模块 1：角色语言风格档案

### 问题诊断

当前角色"太会说话"——台词完整、优雅、直抒胸臆。真正的人类情绪往往不完整、不优雅、有攻击性、有回避、有嘴硬。

### Schema 新增

在 `worldforger/schemas.py` 新增 `CharacterSpeechProfile`：

```python
class CharacterSpeechProfile(BaseModel):
    """角色语言风格档案——让每个角色说话方式不同，避免所有人像同一个人。"""

    # 句式特征
    avg_sentence_length: Literal["short", "medium", "long", "mixed"] = "mixed"
    # short: 经常只说半句，3-5 字
    # long: 习惯完整叙述

    verbosity: Literal["terse", "normal", "verbose"] = "normal"
    # terse: 能用两个字绝不用三个字

    # 口头禅与习惯
    verbal_tics: list[str] = Field(default_factory=list)
    # 例：["啧", "……算了", "你懂什么"]

    filler_words: list[str] = Field(default_factory=list)
    # 例：["那个……", "怎么说呢", "嗯"]

    # 情绪表达方式
    emotional_expression: Literal["direct", "indirect", "suppressed", "explosive", "sarcastic"] = "direct"
    # direct:    "我很生气"
    # indirect:  "……没什么"（但攥紧了拳头）
    # suppressed: 不说话，用动作表达
    # explosive:  "你到底想怎样？！"
    # sarcastic: "哦，真棒，太好了"（反话）

    # 对话行为模式
    confrontation_style: Literal["faces_it", "deflects", "withdraws", "escalates"] = "faces_it"
    # faces_it:   直接面对
    # deflects:   转移话题 / 开玩笑
    # withdraws:  沉默 / 离开
    # escalates:  把冲突升级

    # 回避模式
    avoidance_topics: list[str] = Field(default_factory=list)
    # 例：["家庭", "过去的失败", "对某人的感情"]

    # 沉默的含义
    silence_meaning: str = ""
    # 例："在思考，不是冷漠" / "生气但不想说" / "害怕说错话"

    # 称呼习惯
    address_patterns: dict[str, str] = Field(default_factory=dict)
    # 例：{"char_aila": "队长", "char_grom": "老铁"}

    # 压力下的语言变化
    under_stress: str = ""
    # 例："开始说短句/脏话/或用第三人称指自己"
```

在 `CharactersSection.entities[]` 的每项 dict 中新增可选字段 `speech_profile`。由于 entities 当前是 `list[dict[str, Any]]`（灵活 dict），可以直接写入，无需改 CharactersSection Schema。

### Prompt 注入策略

**修改 `worldforger/story_prompts.py` 的 `build_manuscript_user_payload()`**：

在人物信息中追加语言风格提示：

```
【角色语言风格（请严格遵守以下对话特征）】
- 芬恩：
  - 句式：短句为主，紧张时更短
  - 情绪表达：压抑型——用行动代替语言
  - 回避话题：家庭、过去
  - 沉默时：在思考，不是冷漠
  - 压力下：开始说脏话
- 凯伦：
  - 句式：中等长度，但爱打断别人
  - 情绪表达：讽刺型——用反话表达不满
  - 对抗方式：升级冲突
  - 口头禅："啧"
  - 称呼习惯：叫芬恩"小子"
```

**关键约束 prompt**：
```
【对话真实性规则】
1. 允许角色说话说一半、被打断、转移话题
2. 允许角色说出与自己真实感受相反的话（嘴硬）
3. 不要在对话中"顺便解释世界观"
4. 普通场景的对白应该普通，保留史诗台词给真正重要的时刻
5. 一个人物不会每句话都"精准表达自己的内心"
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterSpeechProfile` |
| `worldforger/story_prompts.py` | `build_manuscript_user_payload()` 注入语言风格 |
| `worldforger/panel_sync.py` | 同步器 characters scope 中提取 speech_profile |
| `static/app.js` | 角色编辑表单中新增语言风格子面板 |

---

## 模块 2：情绪后遗症追踪器

### 问题诊断

角色经历大战/死亡/创伤后，下一章基本恢复正常——这是最明显的 AI 痕迹。真正的人会产生持续的后遗症：失眠、幻听、对特定刺激过敏、不敢独处、情绪失控。

### Schema 新增

扩展 `CharacterRuntimeState`（当前已有 `current_location`、`current_goal`、`emotional_state`、`inventory_changes`、`relationship_updates`、`last_updated_chapter`）：

```python
class EmotionalAftermath(BaseModel):
    """重大事件后角色的持续性心理/生理后遗症"""
    aftermath_id: str = ""               # 唯一 id，如 "am_001"
    source_event: str = ""               # 触发事件简述："第一次接触裂隙核心"
    source_chapter: str = ""             # 触发章节 id
    symptoms: list[str] = Field(default_factory=list)
    # 例：["入睡困难", "对紫色光线过敏", "独处时幻听", "情绪突然低落"]
    intensity: int = Field(default=5, ge=1, le=10)
    # 初始强度 1-10，随章节自然衰减
    trigger_conditions: list[str] = Field(default_factory=list)
    # 例：["看到紫色光", "听到类似裂隙的嗡鸣声", "独处超过一小时"]
    peak_chapter: str = ""               # 症状最严重时的章节
    current_status: Literal["active", "dormant", "resolved", "became_trait"] = "active"
    # active: 当前正在影响角色
    # dormant: 暂时休眠，可能被触发
    # resolved: 经过处理（不是"好了"，而是"学会与之共存"）
    # became_trait: 已固化为角色性格的一部分
    decay_rate: float = 0.3             # 每章自然衰减量（0-1），但触发时会反弹

class CharacterRuntimeState(BaseModel):  # 扩展现有
    # ... 现有字段保持不变 ...
    current_location: str = ""
    current_goal: str = ""
    emotional_state: str = ""
    inventory_changes: list[str] = Field(default_factory=list)
    relationship_updates: dict[str, str] = Field(default_factory=dict)
    last_updated_chapter: str = ""

    # 新增字段
    active_aftermaths: list[EmotionalAftermath] = Field(default_factory=list)
    # 当前活跃的后遗症列表
    aftermath_history: list[EmotionalAftermath] = Field(default_factory=list)
    # 历史后遗症（已 resolved / became_trait），用于回调
```

### 自动提取与更新流程

在 `generate_manuscript()` 完成后（`story_service.py`），追加一次轻量 LLM 调用：

```
【情绪后遗症提取】
给定本章正文，检查是否有角色经历了以下类型的重大事件：
- 生命危险 / 重伤
- 目睹死亡
- 做出重大牺牲
- 信念被颠覆
- 被信任者背叛
- 长时间孤独/被困

对每个受影响的角色，提取：
1. 可能产生的后遗症症状（失眠/噩梦/过敏/恐惧/信任障碍/情绪失控/回避行为）
2. 症状的可能触发条件
3. 初始强度（1-10）

如果角色已有活跃后遗症，检查本章中：
- 是否有症状表现？（如果强度>3但没有任何表现，标注"后遗症被遗忘"）
- 是否有触发条件被激活？
- 是否出现自然衰减或恶化？

输出 JSON：
{"aftermaths": [{"char_id": "xxx", "action": "add|update|resolve", ...}]}
```

### 注入策略

在 `build_manuscript_user_payload()` 中追加：

```
【角色当前携带的后遗症（必须在叙事中体现）】
- 芬恩（am_001：裂隙接触后遗症，强度 6/10，活跃）：
  - 症状：入睡困难、对紫色光敏感、独处时幻听
  - 触发条件：紫色光、裂隙嗡鸣声、独处>1小时
  - 上一章表现：营地有紫色篝火时芬恩刻意坐远了——未明说但读者能察觉
  - 本章要求：至少一处场景中体现症状，可以是细微的（如揉眼睛/叹气/避开某物）
```

**关键约束**：
```
【后遗症叙事规则】
1. 后遗症不一定要被角色自己说出来（用动作暗示更好）
2. 后遗症不一定要在本章被解决或好转
3. 如果本章确实没有合适的触发场景，可以只做极轻微的暗示（一句话）
4. 绝对不要让角色在经历创伤的同一章就产生"感悟→成长"
5. 后遗症可以恶化——不是因为新事件，而是因为日常琐事累积
```

### 衰减机制

在每次章节生成后自动计算：
- `intensity = max(1, intensity - decay_rate)` （自然衰减）
- 若本章触发了后遗症的 `trigger_conditions`，`intensity = min(10, intensity + 2)`
- 若 `intensity <= 2` 且连续 2 章无触发 → 可标记为 `dormant`
- 若某个后遗症持续 5 章以上且 intensity 稳定 → 可标记为 `became_trait`（成为角色的永久特质）

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `EmotionalAftermath`，扩展 `CharacterRuntimeState` |
| `worldforger/story_prompts.py` | 新增 `aftermath_extraction_system()` 和 user payload |
| `worldforger/story_service.py` | `generate_manuscript()` 后调用 aftermath 提取 + 衰减计算 |
| `worldforger/panel_sync.py` | characters scope 同步中写入 aftermath 字段 |
| `static/app.js` | 角色运行时状态卡片中展示活跃后遗症 |

---

## 模块 3：反「成长公式」提示词

### 问题诊断

AI 天然倾向于 `事件 → 感悟 → 成长` 的叙事模式。但真人很多时候不会成长，甚至会退化——更偏执、更激进、更害怕失去、更不愿相信别人。

### 方案（纯 prompt 改动，零 Schema 变更）

这是 P0 中最轻量的改动——不需要新的数据结构，只需要在多个 prompt 中注入"反公式"约束。

**A. Manuscript 生成 prompt 修改**

在 `story_prompts.py` 的 manuscript system prompt 中追加：

```
【关于角色成长——请打破公式】
以下叙事模式是 AI 痕迹，请主动避免：

❌ 事件 → 感悟 → 成长 → 稳定
❌ 失败的下一步就是"学到了教训"
❌ 创伤的同一章就"变得更坚强"
❌ 每个角色每章都在"进步"

真实的人不是这样。请做到：
✅ 允许角色在压力下退化（更偏执、更冲动、更封闭）
✅ 允许角色对同一件事反复摇摆（今天想通了，明天又不行了）
✅ 允许角色嘴硬——明明被说中了但就是不承认
✅ 允许角色"什么都没学到"——有时候人只是撑过去了，不是成长了
✅ 允许情绪的"难看"：嫉妒、迁怒、自我怜悯、逃避
✅ 如果角色确实成长了，用行动而非台词体现
✅ 成长是缓慢的、反复的、不体面的

在本章写作中：
- 如果上一章以失败结尾，本章角色不一定有"新的领悟"
- 如果角色表达了某种成长性认知，接下来让ta在行动中自相矛盾
- 让改变看起来像"不小心发生的"，而非"被总结出来的"
```

**B. 节拍大纲 prompt 修改**

在 `chapter_beats_system()` 中追加：

```
【关于角色弧光——请放慢】
不要在每一个节拍中都安排"角色成长时刻"。
- 有些节拍应该只是"角色撑过去了"
- 有些节拍应该表现"角色比之前更糟了"
- 成长应该留到真正关键的时刻，且只有少数几次
```

**C. 校对者 prompt 增强**（可选，后期）

在校对者检查清单中添加：
```
7. 是否出现 AI 式"感悟→成长"模式？（检查标准：创伤事件后 3 章内不应出现"从中学会/变得更强/理解了"等句式）
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/story_prompts.py` | manuscript system、beats system 增加反公式约束 |
| `worldforger/panel_sync.py` | 校对者检查清单增加"过度成长"检测 |

---

## 模块 4：「呼吸段落」生成模式

### 问题诊断

当前几乎每段都推进剧情/补充设定/建立关系/埋伏笔——太工整，像 PPT 而非小说。真正的人类小说允许"浪费"：扎营时没人说话、盯着火发呆、抱怨鞋子进水。

### 功能设计

**新增工具：`generate_breathing_room`**

用户可在情节对话中触发，或设为自动在每章中插入 1-2 段呼吸段落。

参数：
```json
{
  "characters": ["char_finn", "char_aila"],  // 参与角色（可选，不指定则单人静默）
  "type": "auto",                             // auto | camp | travel | rest | morning | night | meal
  "length": 300,                              // 字数
  "tone": "subtle"                            // subtle（细微）| melancholy（忧郁）| warm（温暖）| tense（紧张下的安静）
}
```

呼吸段落类型：
| 类型 | 示例场景 | 文学效果 |
|:--|:--|:--|
| `camp_silence` | 扎营后无人说话，各自做事 | 让读者和角色一起喘口气 |
| `mundane_complaint` | 抱怨鞋子进水、食物难吃、天气太冷 | 角色更像真人而非英雄 |
| `idle_activity` | 磨斧头、补衣服、盯着火 | 用动作代替台词表达内心 |
| `sleeplessness` | 某人失眠，可能有人注意到 | 暴露角色脆弱面 |
| `unrelated_memory` | 角色想起一件与主线无关的小事 | 给角色过去和厚度 |
| `observation` | 角色注意到环境中一个小细节 | 营造沉浸感和氛围 |
| `body_awareness` | 角色意识到自己很累/饿/冷/伤口痛 | 身体感→真实感 |

### 自动插入模式

在 `generate_manuscript()` 中，新增选项 `breathing_room: "auto" | "none" | number`：
- `"none"`：不插入（默认，保持当前行为）
- `"auto"`：LLM 自行判断是否需要呼吸段落
- `number`（如 2）：每 1000 字插入约 N 段呼吸

自动模式下，prompt 追加：
```
【叙事节奏——请留白】
本章正文中，请包含 1-2 段"无剧情推进"的时刻：
- 可以是一个角色独自沉默
- 可以是队伍间的无意义闲聊
- 可以是对环境/天气/体感的观察
- 可以是角色做一件与主线无关的日常小事

这些段落不需要长（3-5 句即可），但能让读者感受到"这些人是活着的"。
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `BreathingRoomType` 枚举，扩展 `StoryWritingDefaults` 增加 `breathing_room` 字段 |
| `worldforger/story_prompts.py` | 新增 `breathing_room_system()` 和呼吸段落生成 payload |
| `worldforger/story_service.py` | 新增 `generate_breathing_room()` 工具函数，嵌入 `generate_manuscript()` |
| `app/main.py` | 新增 API 端点 `POST /api/worlds/{id}/story/breathing-room` |
| `static/app.js` | 情节工具栏新增"插入呼吸段落"按钮 |

---

## 模块 5：金句密度控制器

### 问题诊断

当前"金句太多"——角色像在轮流发表预告片台词。真正好的史诗感来自平静中的一句话，而非每段都高能。需要追踪史诗台词出现频率，超过阈值时自动降密。

### 检测逻辑

**史诗台词特征匹配**（正则 + LLM 辅助）：

```python
EPIC_PATTERNS = [
    r"为了[一-鿿]+",           # "为了艾瑟兰"
    r"我会(永远|一直|始终)",           # "我会永远站在你前面"
    r"只要我还(活着|在|有)",           # "只要我还活着"
    r"(封印|消灭|拯救|守护)(它|你|我们|这个世界)",  # "封印它"
    r"(成为|变成)(它|你|我们)",        # "成为它"
    r"这是(我的|我们的)(使命|宿命|命运|责任|选择)",  # "这是我的使命"
    r"(绝不|永不|永远不)(放弃|退缩|后退|屈服)",    # "绝不放弃"
    r"我(发誓|起誓|立誓)",             # "我发誓"
    r"(愿|让)[一0-鿿]+(保佑|见证|指引)",  # "愿诸神见证"
]
```

**密度计算**：
```
density = 史诗台词数 / 总对话行数
```

阈值：`epic_density > 0.15`（每 7 句对话中 >1 句史诗）→ 触发警告。

### 两种处理模式

**模式 A：检测 + 警告（低侵入）**

生成后检测→如超标→在前端展示提示："本章金句密度 {density:.0%}，建议将部分台词普通化"。用户可自行编辑。

**模式 B：自动降密（中侵入）**

将检测结果反馈给 LLM，要求重写部分台词：
```
以下台词密度过高，请将其中 2-3 句改写为更日常的表达：
- "我会站在你前面" → 可以改成 "……你别一个人冲"
- "为了艾瑟兰" → 可以改成 "走吧，还磨蹭什么"
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/story_service.py` | 新增 `_detect_epic_density()` 检测函数 |
| `worldforger/story_prompts.py` | 新增密度反馈 prompt（自动降密模式） |
| `static/app.js` | 章节面板展示密度指标 + 降密建议 |

---

## 模块 6：人性缺陷与关系伤害系统

### 问题诊断

当前角色的缺陷更像"可爱的性格标签"——不会真的伤害关系。真人缺陷会伤害身边人：自我感动式救世、控制欲、情绪勒索、逃避责任。

### Schema 设计

在 `worldforger/schemas.py` 新增：

```python
class CharacterFlaw(BaseModel):
    """角色人性缺陷——不只是标签，而是会真实伤害关系的人格问题"""
    flaw_id: str = ""
    name: str = ""                        # 缺陷名称："自我感动式救世"
    category: Literal[
        "emotional",    # 情感型：过度牺牲、情绪勒索、控制欲
        "cognitive",    # 认知型：偏执、非黑即白、过度乐观/悲观
        "behavioral",   # 行为型：逃避、迁怒、成瘾、暴躁
        "relational",   # 关系型：不信任、依附焦虑、利用他人
        "moral",        # 道德型：双标、合理化恶行、极端正义
    ] = "emotional"
    severity: Literal["mild", "moderate", "severe"] = "moderate"
    description: str = ""                 # 该缺陷如何表现

    # 缺陷导致的伤害记录
    damages_caused: list[dict[str, Any]] = Field(default_factory=list)
    # [{"target_char_id": "char_finn", "damage": "让芬恩觉得自己不被信任", "chapter": "ch_3", "resolved": false}]

    # 角色对自己缺陷的认知程度
    self_awareness: Literal["unaware", "beginning_to_see", "struggling", "accepted"] = "unaware"
    # unaware: 完全不觉得自己有问题
    # beginning_to_see: 开始有模糊的不适感
    # struggling: 知道自己有问题但改不了
    # accepted: 接受了但未必改了

    # 缺陷的触发条件
    triggers: list[str] = Field(default_factory=list)
    # 例：["队友受伤时", "计划被打乱时", "被质疑权威时"]

    # 缺陷是否在改善
    arc_status: Literal["worsening", "stable", "slowly_improving"] = "stable"
```

在 `CharactersSection.entities[]` 每项 dict 中新增可选字段 `flaws: list[dict]`。

### Prompt 注入

在 manuscript 生成 prompt 中追加：

```
【角色缺陷——必须在叙事中造成真实伤害】
本章出场的角色各有一个需要在本章中体现的缺陷：
- 艾拉（自我感动式救世 | moderate | unaware）：
  艾拉相信自己必须承担一切，但这会让队友感到被轻视。
  本章要求：至少一处场景中，艾拉独揽责任的行为让队友（尤其是芬恩）感到失望或被排斥。

- 凯伦（嘴臭与不信任 | moderate | beginning_to_see）：
  凯伦用尖刻语言推开他人来保护自己。
  本章要求：凯伦至少一次因嘴臭伤害到队友的感情，即使她自己察觉到了但收不回来。

【缺陷叙事规则】
1. 缺陷不应被浪漫化——它真的让人不舒服
2. 缺陷不需要在本章被解决（甚至不需要被意识到）
3. 不要用旁白解释"她这样是因为……"——让读者自己感受
4. 缺陷的伤害效果应体现在受害角色的反应中，而非仅仅存在于叙述中
```

### 伤害追踪

每章生成后，在 aftermath 提取的同一个 LLM 调用中增加缺陷伤害检测：
```
检查本章中：
1. 各角色的缺陷是否有表现？
2. 如果有表现，是否对他人的情绪/行为产生了实际影响？
3. 如果有影响，记录到 character.relations 中（如 "trust -1"）
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterFlaw` |
| `worldforger/story_prompts.py` | manuscript payload 注入缺陷 + 触发条件 |
| `worldforger/story_service.py` | 章节后缺陷伤害检测 + 更新 |
| `static/app.js` | 角色卡片展示缺陷与伤害历史 |

---

## 模块 7：微观习惯 / 小尺度情感库

### 问题诊断

当前叙事尺度太大——全是世界/裂隙/命运/血脉/阵营。但读者真正记住的通常是"谁记得谁怕冷""谁讨厌药味""谁偷偷保存旧地图"。

### Schema 设计

```python
class CharacterMicroHabit(BaseModel):
    """角色的微观习惯与小尺度特征——让角色存在的细节"""
    habit_id: str = ""
    character_id: str = ""
    habit: str = ""                       # "总是第一个坐到火边——怕冷"
    category: Literal[
        "physical",       # 身体习惯：怕冷、磨牙、走路拖脚
        "behavioral",     # 行为习惯：最后睡、第一个守夜、总检查门锁
        "preference",     # 偏好：讨厌药味、喜欢甜的、坚持用旧杯子
        "memory_anchor",  # 记忆锚点：存旧地图、留破损的护身符、不扔第一件斗篷
        "relationship_detail",  # 关系细节：记得谁不吃蘑菇、知道谁伤口痛
    ] = "physical"
    visibility: Literal["subtle", "noticeable", "signature"] = "subtle"
    # subtle: 需要仔细读才能注意到
    # noticeable: 队友会注意到
    # signature: 角色的标志性特征

    first_shown_chapter: str = ""         # 首次出现的章节
    callback_chapters: list[str] = Field(default_factory=list)
    # 后续回调的章节列表——习惯需要反复出现才有意义

    known_by_characters: list[str] = Field(default_factory=list)
    # 哪些角色知道这个习惯（知道的人越多，关系越深）

    emotional_weight: str = ""
    # 该习惯的情感含义，如："怕冷是因为在北境战役中差点冻死"
```

在 `CharactersSection.entities[]` 每项 dict 中新增可选字段 `micro_habits: list[dict]`。

### 播种与回调机制

**播种**：角色创建时，LLM 为每人生成 3-5 个微观习惯。此后每 3-5 章可追加 1 个新习惯。

**本章要求注入**：
```
【可在本章中自然展现的角色细节（选 1-2 个，不必刻意）】
- 芬恩怕冷，总是离火最近 → 可以一句话带过
- 凯伦讨厌药味 → 如果有人煮药，凯伦皱眉
- 格罗姆的旧斧柄上有刻痕——那是他师父留下的
```

**回调追踪**：每章后检查哪些习惯被使用了，记录到 `callback_chapters`。如果某个习惯超过 5 章未出现，在下章 prompt 中温和提醒。

### 小尺度情感库

每个角色存储 5-10 个"与他人有关的小记忆"：

```python
class SmallMemory(BaseModel):
    """角色之间的小尺度情感记忆"""
    character_id: str = ""               # 谁的记忆
    about_char_id: str = ""              # 关于谁
    memory: str = ""                     # "第一次见面时凯伦给了他一壶热水"
    category: Literal["first_impression", "small_kindness", "argument", "shared_silence", "noticed_detail"] = "small_kindness"
    chapter: str = ""                    # 建立于哪一章
    callback_count: int = 0              # 回调次数
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterMicroHabit`、`SmallMemory` |
| `worldforger/story_prompts.py` | manuscript payload 注入习惯 + 小记忆 |
| `worldforger/story_service.py` | 习惯使用追踪 + 回调提醒 |
| `static/app.js` | 角色卡片展示习惯与记忆 |

---

## 模块 8：设定揭示度追踪器

### 问题诊断

当前角色经常"顺便解释世界观"（"这是翠绿议会古老时期……"），这是西幻 AI 文最明显的问题。神秘感来自不完全理解，而非百科全书。

### Schema 设计

```python
class LoreRevealEntry(BaseModel):
    """单条世界设定的揭示状态追踪"""
    lore_id: str = ""                     # 如 "lor_celestial_council_origin"
    section: str = ""                     # 所属模块：geography/factions/history/...
    name: str = ""                        # "翠绿议会的真正起源"
    summary: str = ""                     # 该设定的完整内容（作者可见）
    reveal_status: Literal[
        "hidden",           # 尚未在正文中出现
        "hinted_very_subtle",  # 极隐晦的暗示（只有重读才能发现）
        "hinted",            # 读者可能能猜到
        "partially_revealed", # 部分揭示
        "fully_revealed",     # 完全揭示
    ] = "hidden"

    # 揭示历程
    reveal_history: list[dict[str, Any]] = Field(default_factory=list)
    # [{"chapter": "ch_2", "type": "hinted_very_subtle", "detail": "古老壁画上出现了与议会徽章相似的符号", "delivered_by": "environment"}]

    # 哪些角色知道此设定
    known_by_characters: list[str] = Field(default_factory=list)
    # 角色之间可以有信息差

    # 还有多少未解之谜
    mystery_remaining: str = ""
    # "议会成员是否真的是初代精灵？他们的力量来源是什么？"

    # 最终揭示计划章节
    planned_reveal_chapter: str = ""
```

在 `schemas.py` 中新增 `LoreRevealTracker` 作为 `World` 的可选字段：
```python
class World(BaseModel):
    # ... 现有字段 ...
    lore_reveal_tracker: list[LoreRevealEntry] = Field(default_factory=list)
```

### 自动检测"顺便解释世界观"

在 manuscript 生成后，用检测 prompt 标记暴露问题：

```
请检查本章正文中是否有以下问题：
1. 角色在对话中"顺便解释"了世界设定（如"你知道的，翠绿议会古老时期……"）——A 和 B 都是这个世界的人，他们不需要向彼此解释常识。
2. 叙述者直接以百科全书口吻解释了某个设定的全部信息。
3. 某个本应保持神秘的设定被过早或过详细地揭示。

对每个问题：
- 标注原文行
- 标注涉及的 lore_id
- 建议修改方式（如"改为角色做了一件与设定相关的行为但不解释"）
```

### Prompt 注入

在 manuscript prompt 中：
```
【设定揭示控制——请保留神秘感】
以下是本章中可以暗示但不应完全解释的设定：
- 翠绿议会的真正起源（reveal_status: hinted_very_subtle）
  → 本章最多：一个环境细节暗示议会的历史比宣称的更久
  → 不要：任何角色口述或思考议会的起源

以下是本章中不应被提及的设定（reveal_status: hidden）：
- 裂隙的本质
- 艾瑟兰的真相

【禁止"顺便解释世界观"】
角色对话中，禁止出现以下句式（及其变体）：
- "你知道的，X 其实是 Y……"
- "很久以前，X 族和 Y 族……"（除非是对一个真的不知道的角色说的）
- "这是 X，远古时期……"

如果不确定：让角色做某件事（如进行一个仪式），但不解释仪式的含义。
读者比你以为的更有耐心——他们不需要立刻理解一切。
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `LoreRevealEntry`，`World` 增加 `lore_reveal_tracker` |
| `worldforger/story_prompts.py` | manuscript prompt 注入揭示控制 |
| `worldforger/story_service.py` | 章节后 lore 揭示检测 + 更新揭示历史 |
| `worldforger/panel_sync.py` | 同步器中支持 lore reveal tracker |
| `static/app.js` | 新增"设定揭示度"面板（各 lore 条目 + 状态 + 揭示进程） |

---

## 模块 9：不可逆失败事件系统

### 问题诊断

当前主角团虽然危险，但读者潜意识知道"他们总能解决"。需要真正不可挽回的失败——NPC 因他们而死、来晚一步、关系崩裂——并且失败不能立刻转化成成长。

### Schema 设计

```python
class IrreversibleFailure(BaseModel):
    """不可逆失败事件——无法修复，只能承受"""
    failure_id: str = ""
    type: Literal[
        "npc_death_caused",       # 因角色决策导致的 NPC 死亡
        "missed_opportunity",     # 来晚一步，错失关键时机
        "wrong_decision",          # 计划完全错误，导致灾难性后果
        "relationship_rupture",    # 角色间关系破裂（不是吵架，是真正崩裂）
        "plan_collapse",           # 核心计划彻底失败
        "loss_of_trust",           # 失去重要人物/群体的信任
    ] = "wrong_decision"
    chapter: str = ""                    # 发生于哪章
    summary: str = ""                    # 发生了什么

    # 直接后果
    immediate_consequences: list[str] = Field(default_factory=list)
    # 例：["北境小镇因他们的错误情报而被毁", "NPC 莫里斯死亡", "凯伦不再信任艾拉的判断"]

    # 长期伤痕（不随章节消失）
    long_term_scars: list[str] = Field(default_factory=list)
    # 例：["艾拉不再信任自己的直觉", "芬恩对情报收集有强迫性焦虑"]

    # 责任归属
    responsible_characters: list[str] = Field(default_factory=list)
    # 谁的责任——可以是多人

    # 冷却追踪
    chapters_since_failure: int = 0       # 自失败以来过了多少章
    min_cooldown_chapters: int = 3        # 必须至少过这么多章才能出现任何正面转化

    # 是否已被"修复"
    resolved: bool = False
    resolution_type: Literal[
        "never",                          # 永远不可逆
        "lived_with",                     # 角色学会了与之共存（不是好了）
        "partial_acceptance",             # 部分接受
        "scar_became_part_of_them",       # 伤痕成为角色人格的永久组成部分
    ] = "never"

    # 连锁效应
    cascaded_to: list[str] = Field(default_factory=list)
    # 此失败导致的后续失败/问题 id
```

### 核心约束机制

```
【不可逆失败——叙事硬约束】
1. 失败发生后的 3 章内：
   - 禁止：任何角色从该失败中"学到教训"或"变得更强"
   - 禁止：失败被新事件覆盖或淡化
   - 要求：至少一个场景展现角色仍在被此失败影响

2. 失败的表征必须是"不好看的"：
   - 逃避（不愿提及/转移话题）
   - 自我怀疑（反复问"如果当时……"）
   - 迁怒（对其他事发脾气）
   - 功能退化（决策更犹豫或更冲动）

3. 如果失败最终被接受：
   - 不应该是"理解了一切"式的顿悟
   - 而应该是"不再追问为什么"式的沉默接受
   - 变化不应发生在单一章节中
```

### Prompt 注入

在 manuscript 生成 prompt 中追加：

```
【未愈合的伤痕——必须在叙事中承重】
当前世界中存在以下不可逆失败，角色仍在背负其后果：
- fail_001（NPC 莫里斯之死，发生于 ch_5）：
  直接责任人：艾拉（错误情报）、芬恩（执行错误）
  距离失败：2 章（仍在冷却期，禁止成长转化）
  本章要求：至少一处展现此失败仍在影响角色——艾拉怀疑自己的情报判断，或芬恩对类似场景有过度反应
  禁止：任何人说"莫里斯的死让我们变得更强大"或类似台词
```

### 失败事件触发检测

在每章生成后检查：
1. 是否有新的不可逆失败发生？
2. 已有的失败在冷却期内是否被错误地"解决"？
3. 如果有新失败，自动生成 `IrreversibleFailure` 并写入 world.json

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `IrreversibleFailure`，`World` 增加 `irreversible_failures` |
| `worldforger/story_prompts.py` | manuscript payload 注入失败伤痕 |
| `worldforger/story_service.py` | 章节后失败检测 + 冷却期校验 |
| `worldforger/panel_sync.py` | 同步器 story scope 中支持失败事件 |

---

## 模块 10：角色相互改变追踪

### 问题诊断

当前角色关系仍是"共同完成任务→感情加深"的功能模式。真正的角色弧光应该是因为遇见彼此→人格发生变化——芬恩从逃避型→敢承担责任（因为艾拉），艾拉从正确机器→允许自己软弱（因为芬恩）。

### Schema 设计

```python
class CharacterArcStage(BaseModel):
    """角色弧光的一个阶段"""
    chapter: str = ""                    # 本章体现的阶段
    stage_description: str = ""          # "第一次为艾拉留下来，尽管害怕"
    personality_shift: str = ""          # 人格变化的具体描述
    catalyst: str = ""                   # 催化剂（另一个角色/事件）
    catalyst_char_id: str = ""           # 如果是被人影响的，此人的 id
    regression: bool = False             # 是退行（退步）还是前进？
    evidence_in_text: str = ""           # 在本章正文中的具体体现（一段话概括）

class CharacterMutualChange(BaseModel):
    """角色相互改变——不是因为事件，而是因为彼此"""
    change_id: str = ""

    # 主动改变方
    character_id: str = ""               # 被改变的角色
    direction: str = ""                  # "逃避型人格 → 开始敢承担责任"
    catalyst_character_id: str = ""      # 谁的存在导致了此变化
    catalyst_mechanism: str = ""         # 改变机制："艾拉不放弃的态度让芬恩开始相信稳定是可能的"

    # 是否是双向的
    is_reciprocal: bool = False
    reciprocal_change_id: str = ""       # 对应的另一方变化 id

    # 变化阶段（跨越多章）
    stages: list[CharacterArcStage] = Field(default_factory=list)

    # 当前状态
    current_stage: str = ""              # 当前处于哪个阶段
    completed: bool = False              # 变化是否完成
    completion_chapter: str = ""

    # 注意：变化不一定是"好的"——可能一个人让另一个人变得更糟
    direction_sign: Literal["positive", "negative", "mixed"] = "positive"

class CharacterMutualChangeTracker(BaseModel):
    """全局角色相互改变追踪"""
    changes: list[CharacterMutualChange] = Field(default_factory=list)
```

在 `World` 中新增：
```python
character_mutual_changes: CharacterMutualChangeTracker = Field(
    default_factory=CharacterMutualChangeTracker
)
```

### 初始化与更新

**初始化**：角色创建时，LLM 预判可能的角色弧光方向（可空，留待情节发展后补充）。

**检测时机**：每 3 章运行一次角色弧光检测（与 aftermath 提取合并或独立调用）：

```
【角色相互改变检测】
请对比当前章节和 3 章前的角色状态，检查是否有以下迹象：
1. 某个角色的行为模式/决策方式/情感反应出现了系统性变化
2. 这种变化是否可以追溯到另一个角色的持续影响（不是单一事件）
3. 变化是否在多个场景中一致体现（不是一次性的）

对每个检测到的变化：
- 如果变化已经存在于 tracker 中：追加新的 stage
- 如果变化是新出现的：创建新的 MutualChange 记录

注意：
- 变化不一定是"好的"——角色也可以因为彼此变得更糟
- 变化应该是缓慢的、不一致的——今天进步了明天可能又退回去
- 不要每章都发现新变化——真正的改变以 3-5 章为单位
```

### Prompt 注入

在 manuscript 生成 prompt 中：

```
【角色间深层影响——本周期的弧光方向】
当前追踪中的角色相互改变：
- 芬恩 ← 艾拉的影响：
  方向：逃避型 → 敢承担责任（mixed，反复中）
  当前阶段（ch_5）：第一次主动承担但不是为了艾拉——开始内化
  本章提示：可以在一个不起眼的时刻让芬恩自己做了一个负责任的选择，不需要艾拉在场

- 艾拉 ← 芬恩的影响：
  方向：正确机器 → 允许自己软弱（early）
  当前阶段（ch_3）：艾拉在芬恩面前第一次承认"我不知道怎么办"
  本章提示：可以展现艾拉在自己的决策上犹豫，看向芬恩——不是求助，而是确认自己不是一个人

【弧光叙事规则】
1. 角色变化不能由旁白说出——必须由行动和选择体现
2. 不能每章都有"重大进展"——有时一整章没有弧光变化是正常的
3. 退步是弧光的一部分——不要跳过退步直接到成长
4. 最终的变化应该是"不小心发生的"——角色自己可能都没意识到
```

### 涉及文件

| 文件 | 改动 |
|:--|:--|
| `worldforger/schemas.py` | 新增 `CharacterArcStage`、`CharacterMutualChange`、`CharacterMutualChangeTracker`，`World` 增加字段 |
| `worldforger/story_prompts.py` | 新增弧光检测 prompt `mutual_change_detection_system()`；manuscript payload 注入弧光方向 |
| `worldforger/story_service.py` | 每 3 章触发弧光检测；`generate_manuscript()` 注入弧光上下文 |
| `worldforger/panel_sync.py` | 同步器 story scope 中支持 mutual changes |
| `static/app.js` | 新增"角色弧光"面板（角色间影响关系图 + 各阶段展示） |

---

## 实施路径

```
Phase 1（2-3 周）──────────── Phase 2（3-4 周）──────────── Phase 3（4-6 周）──
├─ 模块 1: 角色语言风格档案    ├─ 模块 4: 呼吸段落生成模式    ├─ 模块 8: 设定揭示度追踪
├─ 模块 2: 情绪后遗症追踪器    ├─ 模块 5: 金句密度控制器      ├─ 模块 9: 不可逆失败系统
├─ 模块 3: 反成长公式提示词    ├─ 模块 6: 人性缺陷与关系伤害  ├─ 模块 10: 角色相互改变追踪
                               └─ 模块 7: 微观习惯/小尺度情感库
```

### Phase 1 策略

P0 三个模块的共同特征是：**改动集中在 Schema + Prompt，不对现有管线做结构性改造**。

1. **模块 3 最先做**（零 Schema 改动，纯 prompt，当天可完成测试）
2. **模块 2 第二**（扩展已有 `CharacterRuntimeState`，有前例可循）
3. **模块 1 第三**（新增 Schema 但无复杂管线逻辑）

Phase 1 完成后，生成的小说应已有明显改善：
- 角色对话不再千篇一律
- 创伤不会"下一章就好了"
- 不再强制每章都有"成长"

### Phase 2 策略

P1 四个模块需要新增生成/检测功能，对现有管线有扩展。

1. **模块 7 先做**（Schema 简单，prompt 注入直观，效果立竿见影）
2. **模块 6 其次**（依赖模块 2 的 aftermath 提取管线）
3. **模块 4 第三**（需要新增工具，但独立于其他模块）
4. **模块 5 最后**（检测逻辑需要较多调试）

### Phase 3 策略

P2 三个模块是深度追踪系统，需要跨越多章的累积数据才能发挥作用。建议在 Phase 1+2 稳定运行至少 10 章后再启动。

---

## 注意事项

1. **这些模块是"文学增强"而非"结构修正"**——它们修改的是生成内容的质感和纹理，不影响世界构建和剧情结构的正确性。
2. **全部模块的 prompt 注入都应该是可开关的**——通过 `StoryWritingDefaults` 或环境变量控制，允许用户根据需要启用/关闭特定模块。
3. **检测类功能（密度/揭示度/失败冷却）应以"温和提醒"方式呈现**——标注在章节 `author_notes` 中，不阻止生成。
4. **不要过度自动化**——很多文学判断（如"这句话是否太史诗"）需要人的审美感知，AI 检测只是辅助。
