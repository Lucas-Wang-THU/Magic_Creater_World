---
name: worldforger-story
description: >-
  在 Magic_Creater_World 仓库中设计、编辑或生成 world.json 的 story（情节）节与 story/ 目录下 Markdown：
  粗纲 macro_outline、细纲 beats、文稿 manuscript、伏笔 foreshadowing、叙事人物与人称。
  在用户或对话提到情节板块、章节文稿、粗纲细纲、POV、第一/第三人称、伏笔可视化时使用。
---

# 情节（story）· 协作要点

## 数据形态

- **顶层键**：`story`（`worldforger/schemas.py` 的 `StorySection`）。
- **单元标签** `unit_label`：小说默认 **章**；游戏 **章节**；CoC/DnD **跑团会话**（可由 `meta.creative_mode` 推导）。
- **人称** `narrator.person`：`first_person` | `third_person_limited` | `third_person_omniscient`。
- **文件**：`worlds/<id>/story/macro_outline.md`、`beats/<chapter_id>.md`、`manuscript/<chapter_id>.md`。
- **大纲页保留**：`POST …/outline` 的 `characters` / `plot` 仍写入 `outlines/`，与 `story` 分工不同。

## API（`app/main.py`）

- `GET/PUT …/story/macro-outline`、`…/chapters/{id}/beat|manuscript`
- `POST …/story/chapters`、`DELETE …/chapters/{id}`
- `POST …/story/generate/macro-outline|chapter-beats|manuscript`
- `POST …/story/import-legacy-outline`（从 `outlines/plot_outline.md` 导入粗纲）

## 前端

- 工作台 **情节构建**（`#view-storyChat`）：`POST …/story-chat`，对话后 `scope=story` 同步并跳转情节子栏。
- 导航 **情节**：总览 / 大纲（粗纲+细纲+辅助大纲）/ 章节 / 伏笔 / 写作（`#view-story`）；Markdown 预览用 `renderAssistantMarkdownHtml`；**作者视图** 可显示 `## 作者备注` 区块。
- 情节构建回复中 `story-macro` / `story-beat:id` / `story-manuscript:id` 代码块可一键写入磁盘。

## 勿

- 勿将长篇文稿默认走 `sync-panels-from-chat`（第二路仅用于 world.json 设定节）。
