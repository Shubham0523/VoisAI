"""Runs when a call ends: roll up metrics, update the level estimate, build the optional
recap card, summarise the conversation into memory, and close follow-ups we asked about."""

import logging
from collections import Counter
from statistics import mean

from sqlalchemy import select

from voisai import clock, llm
from voisai.db.models import ConversationSession, Observation, SkillMastery, Turn, User, VocabItem
from voisai.db.session import db
from voisai.memory import store
from voisai.tutor import metrics
from voisai.tutor.learner_model import Mastery
from voisai.tutor.skills import SKILL_BY_ID
from voisai.tutor.wordbank import WORD_BY_KEY

log = logging.getLogger("voisai.session_end")


def _avg(vals: list[float]) -> float | None:
    vals = [v for v in vals if v is not None]
    return round(mean(vals), 2) if vals else None


async def finalize_session(session_id: str, summarize: bool = True) -> dict:
    async with db() as s:
        sess = await s.get(ConversationSession, session_id)
        if sess is None:
            return {}
        user_id = sess.user_id
        plan = sess.plan or {}
        turns = list(
            (
                await s.execute(
                    select(Turn).where(Turn.session_id == session_id).order_by(Turn.idx)
                )
            ).scalars()
        )
        turn_ids = [t.id for t in turns]
        obs = (
            list(
                (
                    await s.execute(select(Observation).where(Observation.turn_id.in_(turn_ids)))
                ).scalars()
            )
            if turn_ids
            else []
        )
        mastery = {
            r.skill_id: Mastery(r.alpha, r.beta)
            for r in (
                await s.execute(select(SkillMastery).where(SkillMastery.user_id == user_id))
            ).scalars()
        }
        used_words = list(
            (
                await s.execute(
                    select(VocabItem.word).where(
                        VocabItem.user_id == user_id, VocabItem.first_used_session_id == session_id
                    )
                )
            ).scalars()
        )

        user_turns = [t for t in turns if t.role == "user"]
        utterances = [t.text for t in user_turns]
        toks = [tok for u in utterances for tok in metrics.tokens(u)]
        errors = [o for o in obs if not o.correct]
        targets = set(plan.get("target_skills", []))
        tgt_obs = [o for o in obs if o.skill_id in targets]
        flu = [t.fluency for t in user_turns if t.fluency]
        bench_turns = [t for t in user_turns if t.benchmark]

        m = {
            "user_turns": len(user_turns),
            "user_words": len(toks),
            "errors": len(errors),
            "errors_per_100w": round(len(errors) / len(toks) * 100, 2) if toks else None,
            "target_accuracy": round(sum(o.correct for o in tgt_obs) / len(tgt_obs), 3)
            if tgt_obs
            else None,
            "mattr": metrics.mattr(toks),
            **metrics.complexity(utterances),
            "wpm": _avg([f.get("wpm") for f in flu]),
            "fillers_per_100w": _avg([f.get("fillers_per_100w") for f in flu]),
            "long_pauses_per_turn": _avg([f.get("long_pauses") for f in flu]),
            "words_used": used_words,
            "target_skills": sorted(targets),
            "benchmark": bool(bench_turns),
        }
        level = metrics.estimate_cefr(mastery, m["mattr"])
        m["cefr"] = level

        sess.metrics = m
        sess.ended_at = sess.ended_at or clock.now()
        sess.is_benchmark = bool(bench_turns)
        sess.recap = build_recap(errors, obs, used_words, plan.get("target_words", []))
        user = await s.get(User, user_id)
        if user and level:
            user.estimated_cefr = level

    if plan.get("followup_ids"):
        await store.resolve(plan["followup_ids"])

    if summarize and len(user_turns) >= 2:
        try:
            summary = await _summarize(turns)
            async with db() as s:
                (await s.get(ConversationSession, session_id)).summary = summary
            await store.remember(user_id, session_id, [(summary, "event", None)])
        except Exception:
            log.exception("summary failed")
    return m


def build_recap(
    errors: list[Observation], obs: list[Observation], used: list[str], targets: list[str]
) -> dict | None:
    """The optional 'by the way' card: one thing to polish, one win, one word. Deterministic:
    picked from stored evidence, so it can never invent a mistake the learner didn't make."""
    card: dict = {}
    confident = [e for e in errors if e.confidence >= 0.85 and e.correction]
    if confident:
        top_skill, _ = Counter(e.skill_id for e in confident).most_common(1)[0]
        ex = max((e for e in confident if e.skill_id == top_skill), key=lambda e: e.confidence)
        card["polish"] = {
            "skill": SKILL_BY_ID[top_skill].name,
            "you_said": ex.span,
            "natural": ex.correction,
        }
    wins = Counter(o.skill_id for o in obs if o.correct)
    if wins:
        sid, n = wins.most_common(1)[0]
        card["win"] = {"skill": SKILL_BY_ID[sid].name, "times": n}
    word = (used or targets or [None])[0]
    if word and word in WORD_BY_KEY:
        card["word"] = {
            "word": word,
            "meaning": WORD_BY_KEY[word].gloss,
            "you_used_it": word in used,
        }
    return card or None


async def _summarize(turns: list[Turn]) -> str:
    convo = "\n".join(f"{'User' if t.role == 'user' else 'Maya'}: {t.text}" for t in turns[-30:])
    return await llm.chat(
        "analyst",
        [
            {
                "role": "system",
                "content": "Summarise this conversation in 2 sentences from Maya's point of view, as "
                "notes a friend would keep: what the user talked about and anything to follow up on. "
                "Write in third person about the user. No commentary on their English.",
            },
            {"role": "user", "content": convo},
        ],
        temperature=0.2,
    )
