# Magic Creater World — 任务与路线图

> 本地调试（与终端一致）：  
> `& E:/ananconda/envs/Agent/python.exe d:/Magic_Creater_World/run.py`  
> 可加 `--no-browser`、`--reload` 等参数。  
> 测试：`E:/ananconda/envs/Agent/python.exe -m pytest tests -q`

---

## 当前状态（最近一次核对）

- **pytest**：`44 passed`（使用 `E:/ananconda/envs/Agent/python.exe`）。
- **地理结构化同步**：`structure_normalize` 对 `geography` 归一化；**仍不能保证模型输出 100% 合法**。失败时 `apply_structure_patch` 跳过该节并写入 `merge_warnings`（前端 toast「校验提示」）。**归一化改写**（如压平 landmarks、补区域 id）通过接口字段 **`normalize_notes`** 返回，前端 toast「结构归一化：…」。

---

## 地理结构化：已实现与边界

### 已实现（归一化 + 提示词）

- `landmarks` / `resources`：对象数组、多行/逗号字符串 → `list[str]`。
- `regions`：单对象 → 单元素数组；`relations` 单对象 → 单元素数组；常见字段别名（`title`、`desc`、`target` 等）。
- 整节 `geography` 为 JSON 字符串 → 解析后再归一化。
- 误把 **区域数组** 放在 `geography` 顶层（值为 `list[dict]`）→ 包成 `{ "regions": … }`。
- **无 `id` 或整段为纯地名字符串** 的区域 → 写入稳定占位 **`rg_` + 12 位十六进制**（便于 `relations.target_id` 不断边）。
- `panel_sync.STRUCTURE_SYSTEM_BASE` 中已强调字段形态，并在规则 9 末附 **短 JSON 形态示例**（虚构名）。

### 仍可能失败或需人工的情形（属预期）

- 模型输出 **非 JSON**、截断、或 `geography` 为 **数字/布尔** 等无法挽救的类型 → 整键丢弃或整节校验失败。
- `regions` 内元素 **全非对象**（如全是字符串且又不符合「整段当名称」规则）→ 可能被过滤为空，与预期不符。
- **空数组 `[]`**：与 `merge_section_conservative` 策略一致，对已有非空列表可能 **不覆盖**（防误删）；与「模型想清空」冲突时需用户手动改表单。
- **关系 `target_id`** 指向不存在区域：结构合法，但关系图语义需用户自行对齐 id。

### 建议观测方式

- 对话后同步：若地理未更新，看 **校验提示**（`merge_warnings`）是否含 `geography:`；若已合并但形态被改过，看 **`normalize_notes`** 或前端「结构归一化」toast。
- 开发时可在 `apply_structure_patch` 对 `geography` 失败分支打日志（按需，勿提交敏感数据）。

---

## 下一步计划（按优先级）

| 优先级 | 项 | 说明 |
|:--:|:--|:--|
| P1 | **结构化同步可观测性** | ~~接口返回 `normalize_notes`；前端 toast「结构归一化」~~ **已完成**。 |
| P1 | **地理专项回归用例** | ~~`test_apply_geography_patch_after_normalize_no_warnings` 断言 `rg_` id 与 notes；`test_normalize_structure_patch_detailed_notes_geography_json_string`~~ **已补**。 |
| P2 | **第二路 Prompt 小样本** | ~~`STRUCTURE_SYSTEM_BASE` 规则 9 末合法 `geography` 短 JSON 示例~~ **已完成**。 |
| P2 | **regions 与 id 稳定性** | ~~无 id 区域生成 `rg_` + 哈希~~ **已完成**。 |
| P3 | **faction / history 归一化** | 对标 geography，对常见别名/单对象数组做防御性 normalize（按需迭代）。 |
| P3 | **README / html.md** | ~~README：产品地图 Mermaid、职业晋升说明、下游角色路线~~ **已更新**；`html.md` 若存在则补充「同步失败时看 merge_warnings」说明。 |
| P3 | **世界 CRUD** | ~~`PATCH` 重命名显示名、`DELETE` 删目录；前端重命名/删除按钮~~ **已完成**（若需「改目录 id」另立项，牵涉引用迁移）。 |

---

## 下游任务：角色、主角团与关系网络

> 与 [`README.md`](README.md)「后续路线：角色与关系网络」对应；拆 issue 时可按阶段标 `character-*` 前缀。  
> **说明**：独立「人物生成」对话与 `character-chat` 已放在工作台，**不再**作为本节的下游里程碑条目。

### 目标概览

| 能力 | 用户价值 | 依赖 |
|:--|:--|:--|
| **主角团** | 固定 3～7 人核心名单，导出与对话引用一致 | roster 内角色标签 + UI 筛选 |
| **关键配角** | 与派系要人、历史事件对齐，减少设定漂移 | `factions.entities[].key_figures`、`history.events` 参与者字段约定 |
| **人物关系网络** | 一眼看清「谁欠谁、谁背叛谁」 | 结构化 `relations[]` + Mermaid（复用派系图交互） |

### 阶段 A — 数据模型（Pydantic + `world.json`）

- [ ] 在 `World`（或等价根模型）增加 **`characters`**（或命名 `character_roster`）：元素至少含 `id`、`name`、`aliases[]?`、`cast_role`（枚举：`protagonist_core` / `supporting_major` / `supporting_minor` / `antagonist` / `background` 等）、`faction_ids[]?`、`home_region_id?`、`one_line_hook`、`notes`。
- [ ] 增加 **`character_relations`**（或与 `characters[].relations` 内嵌二选一）：`source_id`、`target_id`、`relation_type`（如 `ally` / `rival` / `family` / `debt` / `secret`）、`visibility`（读者已知 / 仅作者）、`notes`。
- [ ] Schema 版本与 **`meta.version`** 或迁移说明对齐；旧世界无该节时前端视为 `[]`。

### 阶段 B — API 与第二路同步

- [ ] `PUT/PATCH` 保存路径已支持新节；**`panel_sync` 白名单**加入 `characters`（及关系节若独立）。
- [ ] `normalize_structure_patch_detailed` 对人物节做别名归一（单对象 → 数组、空串过滤等），并返回 **`normalize_notes`**。
- [ ] 对话后同步：系统提示中附 **短 JSON 示例**（虚构名），避免模型发明未定义字段。

### 阶段 C — 前端工作台

- [x] 左侧 **「角色」** 分区：主角团 / 重要配角 / 人物关系网络 + `characters` 数据子页；关系图宿主（`drawMermaidHost`，`data-mermaid-zoom`）。
- [ ] **主角团**：按 `cast_role` 过滤 chips + 导出 Markdown 小节（与 `markdown_export` 对齐迭代）。
- [ ] **关键配角**：侧栏或卡片展示「关联派系要人 / 历史事件」链接（先做只读解析，再做双向 id 选择器）。

### 阶段 D — 大纲与卡司联动（可选）

- [ ] 大纲 YAML 头扩展：`based_on_characters_version` 可选，便于 diff（与现有「大纲」页生成流程衔接即可）。

### 阶段 E — 质量与测试

- [ ] `pytest`：最小 `characters` patch 合并、非法 `target_id` 进入 **`merge_warnings`**（与地理 linter 同类体验）。
- [ ] 性能：单世界 200+ 角色时关系图分组或分页（远期）。

---

## 世界观功能扩充设想（ backlog，按需取舍）

以下按**与当前代码形态的契合度**分组，便于后续拆 issue；未写优先级的不代表不重要，而是依赖产品定位（偏小说策划 / 偏跑团工具 / 偏游戏文案）。

### A. 数据模型（`World` 新节或扩展现有节）

| 方向 | 价值 | 实现要点 |
|:--|:--|:--|
| **人物 / 角色 roster** | 与派系、历史、地理挂钩，叙事核心 | 详见上文 **「下游任务：角色、主角团与关系网络」**；新顶层如 `characters[]` + 关系边；第二路同步与 `normalize_*` 需同步扩展 |
| **文化 / 族群 / 宗教** | 补充「谁在何种价值观下行动」 | 可先做 `cultures` 或并入 `factions` 的 tags；独立节更易结构化同步 |
| **科技 / 经济 / 交通层** | 与资源、区域关系互补 | 轻量可用 `geography.map_notes` + 长文本；重度再拆 `economy`、`tech` 节 |
| **历法 / 纪年体系** | 历史事件 `when` 字段语义统一 | `meta` 或新 `calendar` 节存「纪元名 ↔ 排序规则」；前端时间轴可选排序 |
| **神话 / 宇宙观 / 源头事件** | 与力量体系、历史勾连 | `cosmology` 或 `history` 子类型（tag：`myth`） |
| **生态 / 危险物种** | 冒险向、游戏向 | `bestiary` 或 `geography` 下扩展字段；注意与现有 `regions` 图可视化一致 |

### B. 关联与一致性（在不大改 schema 前可做）

| 方向 | 价值 | 实现要点 |
|:--|:--|:--|
| **引用校验（linter）** | 地理 `target_id`、历史 `linked_faction_ids`、派系 `relations.target_id` 是否存在 | ~~`GET /api/worlds/{id}/lint-references`；侧栏「数据 → 引用一致性」+ 保存后静默再跑；含文化关系、职业 `exclusive_faction_id`、技能 `prereq_ids` / `profession_id`~~ **已做** |
| **全局实体注册表** | 减少 id 漂移、便于搜索 | 轻量：`world.json` 外挂 `registry.json`；重量：迁移到小节内统一 `entities` |
| **标签 / 题材标签驱动提示** | `meta.genre_tags` 已有，可强化对话与同步 prompt | ~~`genre_tags_prompt_addon()` 注入对话、结构化同步、大纲 system~~ **已做** |

### C. 体验与工具链

| 方向 | 价值 | 实现要点 |
|:--|:--|:--|
| **全文搜索** | 跨板块找关键词 | ~~`GET /api/worlds/{id}/search?q=` 检索 world.json + world.md；侧栏「数据 → 搜索」~~ **已完成** |
| **导出增强** | 对外协作、打印 | 除 `world.md` 外：关系表 CSV、年表 Markdown 分册、glossary |
| **世界模板 / 复制世界** | 快速开坑 | 复制目录 + 新 `meta.id`；或「仅结构骨架」模板 |
| **对话摘要写入历史** | 长会话后手动/自动把结论落成 `history.events` | 第三路小模型或规则片段；注意与现有「板块同步」边界 |
| **版本快照 /  diff** | 误操作回滚 | `world.json.bak` 或按 `meta.version` 存只读快照（存储成本需策略） |

### D. 结构化同步（第二路）深化

- 新板块一律走：**`STRUCTURE_SYSTEM` 白名单** → **`normalize_structure_patch_detailed` notes** → **保守合并** → **`normalize_notes` 可观测**。
- 对 **factions / history** 先做归一化与 few-shot，再考虑人物表等高频结构，避免 prompt 与校验规则爆炸。

### E. 刻意不急着做的（成本高或易 scope creep）

- 多用户协作与权限、实时共编。
- 内嵌地图编辑器（画布级）；当前 Mermaid 可视化已覆盖「关系可读」。
- 完全自动「从对话生成整本设定书」——与「人类策展 + 表单落盘」定位易冲突。

---

## 架构速记（便于联调）

- **第一路**：自然语言对话（`chat_completion`）。
- **第二路**：`sync_panels_from_dialogue` → `parse_structure_json` → **`normalize_structure_patch_detailed`**（`normalize_structure_patch` 为其首元组）→ `merge_section_conservative` → **各节 `model_validate`**；成功响应含 **`normalize_notes`**。
- **静态前端**：`/static/*`；API：`/api/*`；根路径不整站挂载静态，避免盖住 API。

---

## 已完成（归档）

- [x] 地理 `geography` 归一化、`normalize_structure_patch_detailed` 与 **`normalize_notes`** 全链路（`panel_sync` → API → `app.js` toast）。
- [x] `apply_structure_patch` 四元组返回；区域稳定 id `rg_*`。
- [x] **全文搜索**：`worldforger/world_search.py` + `GET /api/worlds/{id}/search`；侧栏「数据 → 搜索」页 UI。验证：`pytest tests/test_world_search.py tests/test_api.py::test_search_world_endpoint_hits_json_and_md -q`。
- [x] **引用一致性**：`worldforger/reference_linter.py` + `GET /api/worlds/{id}/lint-references`；侧栏「数据 → 引用一致性」与保存后静默校验；`meta.genre_tags` → `genre_tags_prompt_addon` 注入对话 / 同步 / 大纲。
