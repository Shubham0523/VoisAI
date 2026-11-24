"""Applies one turn's analysis to the learner model. This is the only place that
writes Observations / SkillMastery / VocabItem, so the update rules live in one spot."""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from voisai import clock
from voisai.config import get_settings
from voisai.db.models import Observation, SkillMastery, VocabItem
from voisai.db.session import db
from voisai.memory import store
from voisai.tutor.analyst import TurnAnalysis
from voisai.tutor.learner_model import Mastery
from voisai.tutor.wordbank import WORD_BY_KEY, used_in

log = logging.getLogger("voisai.tutor")

# Correct uses are cheap for the Analyst to over-report, errors are costly to get wrong,
# so the two have different bars to count as evidence.
MIN_CONF_CORRECT = 0.5

# Analyses for one learner can finish out of order and at the same moment (a fast Analyst, a
# learner who talks quickly). Mastery is read-modify-write, so updates for a user run one at a
# time; otherwise two turns race to create the same skill row and one turn's evidence is lost.
_user_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)


@dataclass
class TurnOutcome:
    observations: int = 0
    errors: list[tuple[str, str, str | None]] = field(default_factory=list)  # skill, span, fix
    words_used: list[str] = field(default_factory=list)
    memories_added: int = 0


async def apply_analysis(
    user_id: str,
    session_id: str,
    turn_id: str | None,
    user_text: str,
    analysis: TurnAnalysis,
    introduced_words: set[str],
    friend_last_text: str = "",
) -> TurnOutcome:
    async with _user_locks[user_id]:
        return await _apply(
            user_id, session_id, turn_id, user_text, analysis, introduced_words, friend_last_text
        )


async def _apply(
    user_id: str,
    session_id: str,
    turn_id: str | None,
    user_text: str,
    analysis: TurnAnalysis,
    introduced_words: set[str],
    friend_last_text: str,
) -> TurnOutcome:
    out = TurnOutcome()
    err_min = get_settings().recast_min_confidence
    now = clock.now()

    async with db() as s:
        mastery_rows = {
            r.skill_id: r
            for r in (
                await s.execute(select(SkillMastery).where(SkillMastery.user_id == user_id))
            ).scalars()
        }
        for e in analysis.evidence:
            if e.confidence < (MIN_CONF_CORRECT if e.correct else err_min):
                continue
            if turn_id:
                s.add(
                    Observation(
                        user_id=user_id,
                        turn_id=turn_id,
                        skill_id=e.skill_id,
                        correct=e.correct,
                        span=e.span,
                        correction=e.correction,
                        confidence=e.confidence,
                    )
                )
            row = mastery_rows.get(e.skill_id)
            if row is None:
                row = SkillMastery(user_id=user_id, skill_id=e.skill_id, alpha=1.0, beta=1.0)
                s.add(row)
                mastery_rows[e.skill_id] = row
            m = Mastery(row.alpha, row.beta).update(e.correct, weight=e.confidence)
            row.alpha, row.beta, row.last_practiced_at = m.alpha, m.beta, now
            out.observations += 1
            if not e.correct:
                out.errors.append((e.skill_id, e.span, e.correction))

        # Vocabulary uptake. Deterministic, not LLM: a word counts as *used* only if the
        # Friend introduced it earlier and did not just say it in the previous reply
        # (echoing the last sentence is repetition, not acquisition).
        vocab = {
            v.word: v
            for v in (
                await s.execute(select(VocabItem).where(VocabItem.user_id == user_id))
            ).scalars()
        }
        candidates = set(vocab) | introduced_words
        for word in candidates:
            tw = WORD_BY_KEY.get(word)
            if tw is None or not used_in(user_text, tw):
                continue
            if used_in(friend_last_text, tw):
                continue
            v = vocab.get(word)
            if v is None:
                v = VocabItem(user_id=user_id, word=word, introduced_session_id=session_id)
                s.add(v)
            v.times_used = (v.times_used or 0) + 1
            if v.status != "used":
                v.status = "used"
                v.first_used_session_id = session_id
            out.words_used.append(word)

    if analysis.memories:
        try:
            out.memories_added = await store.remember(
                user_id,
                session_id,
                [(m.text, m.kind, m.due_in_days) for m in analysis.memories],
            )
        except Exception:
            log.exception("failed to store memories")
    return out


async def mark_introduced(user_id: str, session_id: str, words: list[str]) -> None:
    if not words:
        return
    async with db() as s:
        existing = set(
            (
                await s.execute(
                    select(VocabItem.word).where(
                        VocabItem.user_id == user_id, VocabItem.word.in_(words)
                    )
                )
            ).scalars()
        )
        for w in words:
            if w not in existing:
                s.add(VocabItem(user_id=user_id, word=w, introduced_session_id=session_id))
