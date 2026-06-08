# -*- coding: utf-8 -*-
"""SceneSimulator -- multi-character interaction orchestrator.

V2: Added intent leakage detection, emotional contagion, diversified
stuck breakers, and improved presence detection.
"""

from __future__ import annotations

from worldforger.agents.types import AgentDecision, AgentSimResult
from worldforger.agents.character_agent import CharacterAgent
from worldforger.agents.pov_filter import POVFilter
from worldforger.llm import chat_completion


class SceneSimulator:
    """Orchestrates multi-character interaction in a single scene."""

    def __init__(self, max_rounds: int = 4):
        self.max_rounds = max_rounds
        self._stuck_count = 0
        self._intent_leaks: list[str] = []

    async def run(
        self,
        agents: dict[str, CharacterAgent],
        pov_character_id: str,
        scene_setup: str,
        macro_events: list[str],
        soft_hints: list[str] | None = None,
    ) -> AgentSimResult:
        decisions: list[AgentDecision] = []
        shadow_events: list[str] = []
        ordered_ids = self._decision_order(agents, pov_character_id)
        self._intent_leaks = []

        for round_idx in range(self.max_rounds):
            round_has_new_action = False

            for char_id in ordered_ids:
                agent = agents[char_id]
                if not self._is_present(char_id, scene_setup, agents, pov_character_id):
                    shadow = await self._generate_shadow_action(agent, scene_setup, macro_events)
                    if shadow:
                        shadow_events.append(shadow)
                    continue

                visible = self._build_visible_context(
                    char_id, scene_setup, decisions, round_idx
                )

                decision = await agent.decide(
                    scene_context=visible,
                    macro_events=macro_events,
                    previous_decisions=decisions,
                    round_index=round_idx,
                )
                decisions.append(decision)
                if decision.intended_action or decision.intended_speech:
                    round_has_new_action = True

                # ── P1: Intent leakage detection ──
                self._detect_intent_leak(decision, decisions, agents)

                # ── P1: Emotional contagion ──
                if decision.emotional_shift and round_idx < self.max_rounds - 1:
                    self._apply_emotional_contagion(decision, agents, char_id)

                if self._should_break_round(decision, decisions):
                    break

            if not round_has_new_action:
                break

            if self._is_stuck(decisions, round_idx):
                breaker = self._inject_stuck_breaker(macro_events, decisions)
                macro_events.append(breaker)

        pov_visible = POVFilter.filter(decisions, pov_character_id)

        return AgentSimResult(
            chapter_id="",
            scene_index=0,
            macro_events=macro_events,
            decision_sequence=decisions,
            pov_visible_events=pov_visible,
            shadow_events=shadow_events,
        )

    # ── P1: Intent leakage detection ──────────────────────────────

    def _detect_intent_leak(
        self, decision: AgentDecision,
        history: list[AgentDecision],
        agents: dict[str, CharacterAgent],
    ) -> None:
        """Check if another character might perceive this character's hidden intent.

        When character A has a hidden_intent and character B has high insight (INS),
        B may partially perceive A's true intention despite A trying to hide it.
        """
        if not decision.hidden_intent or not decision.target_character:
            return
        target_agent = agents.get(decision.target_character)
        if not target_agent:
            return
        # Characters with suppressed/indirect emotional expression are more perceptive
        speech = target_agent.state.speech_profile or {}
        emotion_style = speech.get("emotional_expression", "")
        # "indirect" and "suppressed" expressers are better at reading others
        perceptive = emotion_style in ("indirect", "suppressed")

        if perceptive and len(decision.hidden_intent) > 3:
            leak_msg = (
                f"[意图泄露] {target_agent.state.name} 可能察觉 "
                f"{agents.get(decision.character_id, target_agent).state.name if decision.character_id in agents else decision.character_id}"
                f"的真实意图: {decision.hidden_intent[:80]}"
            )
            self._intent_leaks.append(leak_msg)

    def get_intent_leaks(self) -> list[str]:
        return self._intent_leaks

    # ── P1: Emotional contagion ───────────────────────────────────

    def _apply_emotional_contagion(
        self, source_decision: AgentDecision,
        agents: dict[str, CharacterAgent],
        source_id: str,
    ) -> None:
        """A strong emotional shift from one character subtly affects others.

        Only applies when the emotional shift is intense (contains keywords
        like 愤怒/恐惧/崩溃) and the source character is speaking or acting
        visibly toward others.
        """
        shift = source_decision.emotional_shift
        intense_kw = ("愤怒", "恐惧", "崩溃", "绝望", "狂喜", "暴怒", "歇斯底里")
        if not any(kw in shift for kw in intense_kw):
            return
        if not (source_decision.intended_speech or source_decision.intended_action):
            return

        # Affected characters: those present who observe this
        for cid, agent in agents.items():
            if cid == source_id:
                continue
            # Subtle effect: slightly increase pressure or shift emotional_state
            cur = agent.state.emotional_state or ""
            if "不安" not in cur and "紧张" not in cur and agent.state.pressure_level < 80:
                agent.state.emotional_state = cur + "（受场中情绪波及）" if cur else "微感不安"

    # ── Presence detection (improved) ─────────────────────────────

    def _is_present(
        self, char_id: str, scene_setup: str,
        agents: dict, pov_id: str,
    ) -> bool:
        """Determine if character is present in the scene.

        Checks both character ID and character name in scene_setup.
        The POV character is always present.
        Characters from the beat's character list are considered present.
        """
        if char_id == pov_id:
            return True
        agent = agents.get(char_id)
        if not agent:
            return False
        name = agent.state.name
        # Check by character ID first (more precise)
        if char_id in scene_setup:
            return True
        # Check by name in scene setup
        if name and name in scene_setup:
            return True
        # Check if this character was in the beat's character_involved list
        # (injected as part of scene_setup by the caller)
        return False

    # ── Decision order ────────────────────────────────────────────

    def _decision_order(self, agents: dict, pov_id: str) -> list[str]:
        order = [pov_id]
        for cid in agents:
            if cid != pov_id and cid in agents:
                order.append(cid)
        return order

    # ── Visible context builder ───────────────────────────────────

    def _build_visible_context(
        self, char_id: str, scene_setup: str,
        decisions: list, round_idx: int,
    ) -> str:
        parts = [scene_setup]
        for d in decisions:
            if d.character_id == char_id:
                continue
            if d.target_character == char_id and d.intended_speech:
                parts.append(f"[{d.character_id} 对你说]: {d.intended_speech}")
            elif d.target_character == char_id and d.intended_action:
                parts.append(f"[{d.character_id} 对你]: {d.intended_action}")
            elif d.intended_speech and d.target_character:
                parts.append(f"[你看到 {d.character_id} 对 {d.target_character} 说]: {d.intended_speech}")
            elif d.intended_action:
                parts.append(f"[你看到 {d.character_id}]: {d.intended_action}")
        # Inject intent leaks the character may have perceived
        for leak in self._intent_leaks:
            if char_id in leak:
                parts.append(leak)
        return "\n".join(parts)

    # ── Round break detection ─────────────────────────────────────

    def _should_break_round(self, latest: AgentDecision, history: list) -> bool:
        if len(history) < 2:
            return False
        action = ((latest.intended_action or "") + " " + (latest.intended_speech or ""))
        break_signals = ("离开", "转身走", "不再说话", "沉默",
                         "结束对话", "够了", "走开", "离去")
        return any(s in action for s in break_signals)

    # ── Stuck detection (improved) ────────────────────────────────

    def _is_stuck(self, decisions: list, round_idx: int) -> bool:
        if round_idx < 1:
            return False
        recent = [d for d in decisions if d.decision_round >= round_idx - 1]
        if not recent:
            return False
        passive_kw = ("等待", "观察", "沉默", "站着", "坐着", "看着", "望着")
        all_passive = all(
            not d.intended_speech and
            any(kw in (d.intended_action or "") for kw in passive_kw)
            for d in recent
        )
        if all_passive:
            self._stuck_count += 1
        else:
            self._stuck_count = 0
        return self._stuck_count >= 2

    # ── Stuck breaker (diversified) ───────────────────────────────

    def _inject_stuck_breaker(
        self, existing_events: list[str], decisions: list[AgentDecision],
    ) -> str:
        """Inject a diverse external event to break narrative stagnation."""
        import random

        # Use existing macro events if available
        unused = [e for e in existing_events if "【突发】" not in e]
        if unused and len(unused) > len(existing_events) - len([e for e in existing_events if "【突发】" in e]):
            return f"【突发】{unused[0][:60]}（事件提前触发）"

        # Diversified breakers based on context
        last_actions = " ".join(d.intended_action or "" for d in decisions[-3:])
        breakers = [
            "雾蚀边界轻微波动——远处雕塑发出低频脉冲，所有人都感受到了",
            "远处传来铁器碰撞声——可能有人正在接近",
            "一阵冷风穿过峡道，携带雾蚀微粒——凝痕者的塑痕微微发光",
            "天空掠过一只被雾蚀变异的海鸟，叫声像人类婴儿的啼哭",
            "地面轻微震动——远处可能发生了山体滑坡或雕塑场活跃",
            "雾中飘来一股异常的气味——不是雾蚀常见的铜锈味，而是花香",
        ]
        # Avoid repeating the same breaker
        used = [e for e in existing_events if "【突发】" in e]
        available = [b for b in breakers if b not in used]
        if not available:
            available = breakers

        # Pick a breaker that fits the context (simple heuristic)
        if "沉默" in last_actions or "安静" in last_actions:
            # Characters are waiting/silent — use a sensory disruption
            sensory = [b for b in available if any(kw in b for kw in ("声音", "气味", "脉冲", "震动"))]
            if sensory:
                return f"【突发】{sensory[0]}"
        if "观察" in last_actions or "看着" in last_actions or "望向" in last_actions:
            visual = [b for b in available if any(kw in b for kw in ("掠过", "发光", "波动"))]
            if visual:
                return f"【突发】{visual[0]}"

        return f"【突发】{available[0]}"

    # ── Shadow action generation ──────────────────────────────────

    async def _generate_shadow_action(
        self, agent: CharacterAgent, scene_setup: str,
        macro_events: list[str],
    ) -> str | None:
        prompt = (
            f"你是{agent.state.name}。你不在主场景中（{scene_setup[:200]}）。\n"
            f"你的位置: {agent.state.current_location}\n"
            f"你的目标: {agent.state.current_goal}\n"
            f"世界事件: {'; '.join(macro_events[:3])}\n"
            f"请用一句话描述你在幕后做了什么（可能对后续产生影响的行动）:"
        )
        try:
            raw = await chat_completion(
                [{"role": "system", "content": "你是一个角色。用一句话描述你的幕后行动。"},
                 {"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=200,
                timing_label=f"shadow:{agent.state.character_id}",
            )
            return f"{agent.state.name}: {raw.strip()}" if raw.strip() else None
        except Exception:
            return None
