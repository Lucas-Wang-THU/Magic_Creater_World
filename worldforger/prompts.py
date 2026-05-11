from worldforger.creative_modes import outline_mode_addon

SYSTEM_WORLD_ARCHITECT = """你是「世界观架构师」助手，帮助用户搭建小说、游戏、CoC 或 DnD 跑团用的世界设定。
你必须严格依据用户提供的「当前世界 JSON 设定」进行补充与修订；若用户要求新增内容，需与已有设定自洽，不要自相矛盾。
回答使用简体中文，结构清晰；需要列出条目时使用 Markdown。"""


def system_with_world_json(world_json_text: str) -> str:
    return (
        SYSTEM_WORLD_ARCHITECT
        + "\n\n以下为当前世界的权威设定（JSON）。请以此为事实来源：\n\n```json\n"
        + world_json_text
        + "\n```"
    )


OUTLINE_KIND_INSTRUCTIONS = {
    "characters": "请根据世界设定，输出人物小传与人物关系纲要（Markdown）。不要与世界观矛盾。",
    "plot": "请根据世界设定，输出情节总纲与主要矛盾推进（Markdown）。不要与世界观矛盾。",
}


def outline_system_prompt(
    kind: str, world_block: str, *, creative_mode: str | None = None
) -> str:
    instr = OUTLINE_KIND_INSTRUCTIONS.get(kind, OUTLINE_KIND_INSTRUCTIONS["plot"])
    addon = outline_mode_addon(creative_mode)
    tail = f"\n\n{addon}" if addon else ""
    return (
        "你是小说与跑团策划助手。你必须只依据下面的世界设定进行创作，禁止编造与设定冲突的内容。\n"
        + instr
        + tail
        + "\n\n--- 世界设定（JSON 为主；若包含 world.md 片段，与 JSON 冲突时以 JSON 为准） ---\n\n"
        + world_block
    )
