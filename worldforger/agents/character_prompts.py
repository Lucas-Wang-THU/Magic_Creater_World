# -*- coding: utf-8 -*-
"""Prompt templates for character agent decision-making.

Each character agent receives a system prompt that encodes its
personality, speaking style, goals, fears, flaws, and current state.
The perception prompt provides the immediate scene context.
"""

from __future__ import annotations

from worldforger.agents.types import CharacterAgentState


def build_character_system_prompt(state: CharacterAgentState) -> str:
    """Build the system prompt that makes the LLM become this character."""

    speech = state.speech_profile or {}
    avoid_topics = speech.get("avoidance_topics", [])
    verbal_tics = speech.get("verbal_tics", [])

    # Build speech style description
    emotion_style_map = {
        "direct": "直接说出感受",
        "indirect": "用暗示和动作表达感受，不直接说",
        "suppressed": "压抑情绪不表达",
        "sarcastic": "用反话和讽刺表达不满",
        "explosive": "情绪爆发式表达，可能失控",
    }
    confront_style_map = {
        "faces_it": "直接面对冲突",
        "deflects": "转移话题或开玩笑来回避",
        "withdraws": "沉默或离开",
        "escalates": "把冲突升级",
    }

    emotion_desc = emotion_style_map.get(speech.get("emotional_expression", ""), "自然表达")
    confront_desc = confront_style_map.get(speech.get("confrontation_style", ""), "直接面对")
    silence = speech.get("silence_meaning", "")
    under_stress = speech.get("under_stress", "")

    parts = [
        f"你是 {state.name}。",
        f"",
        f"## 你的说话方式",
        f"- 句式: {speech.get('avg_sentence_length','中等')}",
        f"- 话量: {speech.get('verbosity','正常')}",
        f"- 情绪表达: {emotion_desc}",
        f"- 面对冲突: {confront_desc}",
    ]
    if verbal_tics:
        parts.append(f"- 口头禅: {', '.join(verbal_tics)}")
    if silence:
        parts.append(f"- 你沉默时的含义: {silence}")
    if under_stress:
        parts.append(f"- 压力下你的语言变化: {under_stress}")

    if avoid_topics:
        parts.append(f"\n## 你回避的话题（触及这些你会不舒服，可能转移话题或变得防御）")
        for t in avoid_topics:
            parts.append(f"- {t}")

    parts.extend([
        f"",
        f"## 你内心深处的渴望",
        f"{state.core_desire or '（尚未明确）'}",
        f"",
        f"## 你内心深处的恐惧",
        f"{state.core_fear or '（尚未明确）'}",
        f"",
        f"## 你当前的状态",
        f"- 情绪: {state.emotional_state or '平稳'}",
        f"- 目标: {state.current_goal or '维持现状'}",
        f"- 压力水平: {state.pressure_level}/100",
    ])

    # Active aftermaths
    active_ams = [a for a in (state.active_aftermaths or []) if a.get("intensity", 0) >= 3]
    if active_ams:
        parts.append(f"\n## 你身上带着的旧伤（过去的经历仍在影响你）")
        for am in active_ams:
            symptoms = am.get("symptoms", [])
            triggers = am.get("trigger_conditions", [])
            parts.append(f"- {am.get('source_event','')}: {', '.join(symptoms[:4])}")
            if triggers:
                parts.append(f"  触发条件: {', '.join(triggers[:3])}")

    # Flaws
    if state.flaws:
        parts.append(f"\n## 你的性格缺陷（在特定情况下可能发作）")
        for f in state.flaws[:3]:
            triggers = f.get("triggers", [])
            parts.append(f"- {f.get('name','')}: {f.get('description','')[:80]}")
            if triggers:
                parts.append(f"  触发: {', '.join(triggers[:3])}")

    # Physical state
    injuries = state.physical_state.get("active_injuries", []) if state.physical_state else []
    if injuries:
        parts.append(f"\n## 你的身体状况")
        for inj in injuries[:3]:
            parts.append(f"- {inj}")

    # Activation rules — inject if provided by caller via state extension
    activation_info = getattr(state, '_activation_rules_context', None)
    if activation_info:
        parts.append(f"\n## 你的能力发动规则（必须严格遵守）")
        parts.append("以下是你当前所掌握能力的发动条件。你**不能**在条件不满足时使用这些能力。")
        parts.append("如果你不确定条件是否满足，默认假设**不满足**。")
        for rule in activation_info:
            parts.append(f"- {rule}")

    parts.extend([
        f"",
        f"---",
        f"",
        f"【核心规则】",
        f"1. 你不是在写小说——你是在做决策。不要考虑叙事结构或读者体验。",
        f"2. 你只能基于你自己的知识、信念和感知做决策。你不知道别人心里在想什么。",
        f"3. 你可以（而且应该）犯错——说错话、判断失误、被情绪驱动。",
        f"4. 你的决策不需要推进情节——只需要是你这个人在此刻会做的事。",
        f"5. 你有权保持沉默。你有权改变主意。你有权自相矛盾。",
        f"6. 你的情绪变化不需要理由——人类经常莫名其妙地烦躁或难过。",
        f"",
        f"请用 JSON 格式输出你的决策。",
    ])

    return "\n".join(parts)


def build_character_perception_prompt(
    state: CharacterAgentState,
    scene_context: str,
    macro_events: list[str],
    previous_decisions: list,
    round_index: int = 0,
) -> str:
    """Build the perception/decision prompt for a character in a scene."""

    # Summarize what the character can perceive from previous decisions
    visible_actions = []
    for d in previous_decisions:
        if d.character_id == state.character_id:
            continue  # skip own prior decisions
        if d.target_character == state.character_id:
            action = d.intended_speech or d.intended_action
            if action:
                visible_actions.append(f"- [{d.character_id} 对你说/做]: {action}")
        elif d.intended_action or d.intended_speech:
            visible_actions.append(f"- [你观察到 {d.character_id}]: {d.intended_speech or d.intended_action}")

    macro_block = "\n".join(f"  - {e}" for e in macro_events) if macro_events else "（无特殊事件）"
    prev_block = "\n".join(visible_actions) if visible_actions else "（一切刚开始，你正在观察周围）"

    return f"""## 你所在的地方和正在发生的事
{scene_context}

## 不可改变的事实（你只能应对，不能改变这些事件）
{macro_block}

## 你刚才观察到的事
{prev_block}

---

作为 {state.name}，请决定你在这一刻：

1. **internal_reaction**: 你的内心感受到了什么？触动了什么记忆或恐惧？
2. **emotional_shift**: 你的情绪发生了什么变化？（如 "平静→不安"）
3. **intended_action**: 你想做什么？（一个具体的动作）
4. **intended_speech**: 你想说什么？对谁说？（可以填 null）
5. **target_character**: 说话/行动的对象角色 id（可以填 null）
6. **hidden_intent**: 你不说出来的真实意图是什么？
7. **relationship_changes**: 你对谁的看法变了？（{{}} 表示没有变化）
8. **new_short_term_goal**: 是否产生了新的短期目标？（可以填 null）

输出 JSON 格式，不要输出其他内容。"""
