"""Persists the conversation. Every DB write is best-effort: a database hiccup must never
take down a live voice call, so failures are logged and swallowed."""

import logging

from voisai import clock
from voisai.db.models import ConversationSession, Turn, User
from voisai.db.session import db

log = logging.getLogger("voisai.recorder")


class Recorder:
    def __init__(self, user_id: str, session_id: str):
        self.user_id = user_id
        self.session_id = session_id
        self._idx = 0
        self.enabled = True

    async def start(
        self, plan: dict | None, l1: str | None = None, name: str | None = None
    ) -> None:
        try:
            async with db() as s:
                if await s.get(User, self.user_id) is None:
                    s.add(
                        User(id=self.user_id, native_language=l1 or "Hindi", name=name or "friend")
                    )
                    await s.flush()
                s.add(
                    ConversationSession(
                        id=self.session_id, user_id=self.user_id, plan=plan, started_at=clock.now()
                    )
                )
        except Exception:
            log.exception("DB unavailable; continuing without persistence")
            self.enabled = False

    async def update_plan(self, plan: dict) -> None:
        if not self.enabled:
            return
        try:
            async with db() as s:
                sess = await s.get(ConversationSession, self.session_id)
                if sess:
                    sess.plan = plan
        except Exception:
            log.exception("failed to update plan")

    async def add_turn(self, role: str, text: str, **fields) -> str | None:
        if not self.enabled or not text.strip():
            return None
        turn = Turn(session_id=self.session_id, idx=self._idx, role=role, text=text, **fields)
        self._idx += 1
        try:
            async with db() as s:
                s.add(turn)
            return turn.id
        except Exception:
            log.exception("failed to persist turn")
            return None

    async def set_analysis_ms(self, turn_id: str, ms: int) -> None:
        try:
            async with db() as s:
                t = await s.get(Turn, turn_id)
                if t:
                    t.analysis_ms = ms
        except Exception:
            log.exception("failed to record analysis latency")
