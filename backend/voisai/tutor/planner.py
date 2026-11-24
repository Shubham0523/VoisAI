"""Planner: decides what each session is quietly about, then steers turn by turn.

Two levels:
- `plan_session` (once per call): rank skills by need, pick 2 targets, 2-3 words one band
  above the learner, a follow-up from memory to open with, and whether to run the benchmark.
- `Steer` (every turn): turns the plan into short hidden notes for the Friend.

Notes contain *conversational moves only* ("ask what they did last weekend"), never grammar
terms. Early testing showed that telling the Friend "practise past_simple" makes it start
teaching, which is exactly what the product must never do.
"""

from collections import Counter
from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from voisai import clock
from voisai.db.models import ConversationSession, SkillMastery, User, VocabItem
from voisai.db.session import db
from voisai.memory import store
from voisai.tutor.learner_model import Mastery, priority
from voisai.tutor.skills import SKILL_BY_ID, SKILLS
from voisai.tutor.wordbank import WORD_BY_KEY, WORDS, next_level, used_in

_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]
BENCHMARK_EVERY = 5
BENCHMARK_MOVE = (
    "Ask them to tell you about a trip or a day out they really loved. Let them tell the whole "
    "story; only react with short, warm interest and gentle 'and then?' prompts."
)


class SessionPlan(BaseModel):
    target_skills: list[str] = Field(default_factory=list, max_length=3)
    target_words: list[str] = Field(default_factory=list, max_length=4)
    opener: str | None = None
    followup_ids: list[str] = Field(default_factory=list)
    benchmark: bool = False
    level: str = "B1"
    session_number: int = 1
    rationale: str = ""  # shown on the dashboard, never to the Friend


def rank_skills(
    rows: dict[str, Mastery], l1: str, level: str, recently_targeted: set[str]
) -> list[tuple[str, float]]:
    """Pure function so it's unit-testable. Skips skills more than one band above level."""
    cap = _LEVELS.index(level) + 1 if level in _LEVELS else 3
    scored = []
    for sk in SKILLS:
        if _LEVELS.index(sk.cefr) > cap:
            continue
        m = rows.get(sk.id, Mastery())
        if m.status == "mastered":
            continue
        scored.append((sk.id, priority(m, l1 in sk.l1_prone, sk.id in recently_targeted)))
    return sorted(scored, key=lambda x: -x[1])


async def plan_session(user_id: str, now: datetime | None = None) -> SessionPlan:
    now = now or clock.now()
    async with db() as s:
        user = await s.get(User, user_id)
        l1 = user.native_language if user else "Hindi"
        level = (user.estimated_cefr if user else None) or "B1"
        rows = {
            r.skill_id: Mastery(r.alpha, r.beta)
            for r in (
                await s.execute(select(SkillMastery).where(SkillMastery.user_id == user_id))
            ).scalars()
        }
        n_prev = (
            await s.execute(
                select(func.count())
                .select_from(ConversationSession)
                .where(ConversationSession.user_id == user_id)
            )
        ).scalar_one()
        last = (
            await s.execute(
                select(ConversationSession.plan)
                .where(
                    ConversationSession.user_id == user_id, ConversationSession.plan.is_not(None)
                )
                .order_by(ConversationSession.started_at.desc())
                .limit(1)
            )
        ).scalar()
        vocab = {
            v.word: v.status
            for v in (
                await s.execute(select(VocabItem).where(VocabItem.user_id == user_id))
            ).scalars()
        }

    recently = set((last or {}).get("target_skills", []))
    ranked = rank_skills(rows, l1, level, recently)
    targets = [sid for sid, _ in ranked[:2]]

    # Words: one re-exposure of a word introduced before but never used, plus new ones at i+1.
    want = next_level(level)
    reexpose = [w for w, st in vocab.items() if st == "introduced" and w in WORD_BY_KEY][:1]
    fresh = [w.word for w in WORDS if w.level == want and w.word not in vocab]
    if len(fresh) < 2:
        fresh += [w.word for w in WORDS if w.word not in vocab and w.word not in fresh]
    words = reexpose + fresh[: 3 - len(reexpose)]

    followups = await store.due_followups(user_id, now)
    opener = None
    if followups:
        opener = (
            f"Greet them like an old friend and ask how this went: {followups[0].text}. "
            "Keep it to two short sentences."
        )
    elif n_prev > 0:
        opener = (
            "Greet them warmly like a friend you talk to every day and ask how their day is "
            "going. Two short sentences."
        )

    session_number = n_prev + 1
    benchmark = session_number == 2 or (
        session_number > 2 and (session_number - 2) % BENCHMARK_EVERY == 0
    )

    why = []
    for sid in targets:
        m = rows.get(sid)
        why.append(
            f"{sid}: {'no evidence yet' if m is None else f'mastery {m.mean:.2f} ({m.status})'}"
        )
    return SessionPlan(
        target_skills=targets,
        target_words=words,
        opener=opener,
        followup_ids=[f.id for f in followups[:1]],
        benchmark=benchmark,
        level=level,
        session_number=session_number,
        rationale="; ".join(why) or "cold start",
    )


class Steer:
    """Per-turn hint generator. Stateful within a session, cheap, deterministic."""

    def __init__(self, plan: SessionPlan):
        self.plan = plan
        self.turn = 0
        self.words_said: set[str] = set()
        self.benchmark_asked = False
        self.awaiting_benchmark_answer = False
        self.session_errors: Counter[str] = Counter()
        self._skill_i = 0
        self.to_model: str | None = None

    def observe_assistant(self, text: str) -> list[str]:
        """Returns target words the Friend just introduced for the first time."""
        new = []
        for w in self.plan.target_words:
            tw = WORD_BY_KEY.get(w)
            if tw and w not in self.words_said and used_in(text, tw):
                self.words_said.add(w)
                new.append(w)
        return new

    def observe_errors(self, errors: list[tuple[str, str, str | None]]) -> None:
        """(skill_id, span, correction) from the Analyst, already confidence-filtered."""
        self.session_errors.update(sid for sid, _, _ in errors)
        for _, _, fix in errors:
            if fix and len(fix.split()) <= 6:
                self.to_model = fix  # latest wins: the freshest error is the most relevant

    def _skills(self) -> list[str]:
        # A skill the learner keeps tripping over this session joins the targets (in-session
        # adaptivity): the recast already happened, so give them a chance to use it again.
        dynamic = [s for s, n in self.session_errors.most_common(2) if n >= 2]
        return list(dict.fromkeys(self.plan.target_skills + dynamic))

    def next_hint(self) -> str | None:
        self.turn += 1
        self.awaiting_benchmark_answer = False
        parts: list[str] = []
        if self.plan.benchmark and not self.benchmark_asked and self.turn >= 3:
            parts.append(BENCHMARK_MOVE)
            self.benchmark_asked = True
            self.awaiting_benchmark_answer = True
        elif self.turn >= 2 and self.turn % 2 == 0 and (skills := self._skills()):
            sk = SKILL_BY_ID[skills[self._skill_i % len(skills)]]
            self._skill_i += 1
            parts.append(f"Conversation idea for when the moment is right: {sk.elicit}")
        if self.to_model:
            parts.append(
                f'In your reply, naturally use the phrase "{self.to_model}" in your own sentence '
                "(about yourself or them), without referring back to how they said it."
            )
            self.to_model = None
        pending = [w for w in self.plan.target_words if w not in self.words_said]
        if pending and self.turn >= 2:
            parts.append(f'If it fits naturally, use the expression "{pending[0]}" in your reply.')
        if not parts:
            return None
        return " ".join(parts) + " Stay a friend: never comment on their English."
