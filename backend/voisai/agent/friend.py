"""The Friend: the real-time agent. Its only jobs are to be fast and warm.
All the analysis happens in the Tutor, which reaches the Friend only through
hidden [tutor] notes injected into the LLM context for one turn.

Hooks live in `llm_node`, which runs before every generation in both voice and text
mode, so the eval harness exercises exactly the same code path as a real call."""

import asyncio
import logging
import time
from collections.abc import AsyncIterable

from livekit import rtc
from livekit.agents import Agent, ModelSettings, llm, stt

from voisai.agent.persona import FRIEND_INSTRUCTIONS
from voisai.agent.recorder import Recorder
from voisai.tutor import analyst, fluency, service
from voisai.tutor.planner import SessionPlan, Steer

log = logging.getLogger("voisai.friend")

HISTORY_ITEMS = 24  # ~12 exchanges of context for the Friend


class FriendAgent(Agent):
    def __init__(
        self,
        recorder: Recorder,
        plan: SessionPlan,
        l1: str,
        memory_context: str = "",
        analyze: bool = True,
    ):
        instructions = FRIEND_INSTRUCTIONS
        if memory_context:
            instructions += (
                "\n\nWhat you remember about this friend (bring things up naturally, don't list "
                f"them):\n{memory_context}"
            )
        super().__init__(instructions=instructions)
        self.recorder = recorder
        self.plan = plan
        self.steer = Steer(plan)
        self.l1 = l1
        self.analyze = analyze
        self.last_hint: str | None = None
        self.outcomes: list[service.TurnOutcome] = []
        self._words: list[fluency.Word] = []
        self._last_user_id: str | None = None
        self._last_assistant = ""
        self._bg: set[asyncio.Task] = set()

    # --- Voice only: keep word timings + confidences (lost once text reaches the LLM).
    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent]:
        async for ev in Agent.default.stt_node(self, audio, model_settings):
            if ev.type == stt.SpeechEventType.FINAL_TRANSCRIPT and ev.alternatives:
                for w in ev.alternatives[0].words or []:
                    conf = w.confidence if isinstance(w.confidence, float) else None
                    self._words.append(fluency.Word(str(w), w.start_time, w.end_time, conf))
            yield ev

    async def llm_node(
        self, chat_ctx: llm.ChatContext, tools: list[llm.Tool], model_settings: ModelSettings
    ):
        user_msg = next(
            (
                i
                for i in reversed(chat_ctx.items)
                if getattr(i, "type", None) == "message" and i.role == "user"
            ),
            None,
        )
        # Keep the persona/memory instructions plus recent turns only: replies stay fast and a
        # long call can't outgrow the provider's tokens-per-minute budget.
        chat_ctx = chat_ctx.copy().truncate(max_items=HISTORY_ITEMS)
        if user_msg is not None and user_msg.id != self._last_user_id:
            self._last_user_id = user_msg.id
            benchmark_answer = self.steer.awaiting_benchmark_answer
            hint = self.steer.next_hint()
            self.last_hint = hint
            if hint:
                chat_ctx.add_message(role="system", content=f"[tutor] {hint}")
            words, self._words = self._words, []
            self._spawn(
                self._record_and_analyze(user_msg.text_content or "", words, hint, benchmark_answer)
            )
        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            yield chunk

    def on_assistant_message(self, text: str) -> None:
        self._last_assistant = text
        new_words = self.steer.observe_assistant(text)
        self._spawn(self.recorder.add_turn("assistant", text))
        if new_words and self.recorder.enabled:
            self._spawn(
                service.mark_introduced(self.recorder.user_id, self.recorder.session_id, new_words)
            )

    async def _record_and_analyze(
        self, text: str, words: list[fluency.Word], hint: str | None, benchmark: bool
    ) -> None:
        prev_assistant = self._last_assistant
        metrics = fluency.compute(words)
        turn_id = await self.recorder.add_turn(
            "user",
            text,
            words=[w.__dict__ for w in words] or None,
            fluency=metrics.as_dict() if metrics else None,
            hint=hint,
            benchmark=benchmark,
        )
        if not self.analyze or not self.recorder.enabled:
            return
        try:
            t0 = time.perf_counter()
            result = await analyst.analyze_turn(text, prev_assistant, self.l1)
            outcome = await service.apply_analysis(
                self.recorder.user_id,
                self.recorder.session_id,
                turn_id,
                text,
                result,
                introduced_words=self.steer.words_said,
                friend_last_text=prev_assistant,
            )
            self.steer.observe_errors(outcome.errors)
            self.outcomes.append(outcome)
            if turn_id:
                await self.recorder.set_analysis_ms(turn_id, int((time.perf_counter() - t0) * 1000))
        except Exception:
            log.exception("analyst failed")

    def _spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self._bg.add(t)
        t.add_done_callback(self._bg.discard)

    async def drain(self) -> None:
        while self._bg:
            await asyncio.gather(*list(self._bg), return_exceptions=True)
