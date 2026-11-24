"""Read models for the growth dashboard and the eval page.

Mastery history is *replayed* from stored observations through the same update rule the
Tutor uses, rather than snapshotted. Beliefs are derived from evidence, so the chart can
never drift from what the learner actually said."""

import json
from collections import defaultdict
from pathlib import Path

from sqlalchemy import func, select

from voisai.config import get_settings
from voisai.db.models import ConversationSession, Observation, SkillMastery, Turn, User, VocabItem
from voisai.db.session import db
from voisai.tutor.learner_model import Mastery
from voisai.tutor.service import MIN_CONF_CORRECT
from voisai.tutor.skills import SKILL_BY_ID
from voisai.tutor.wordbank import WORD_BY_KEY

SIM_RESULTS = Path(__file__).resolve().parents[2] / "sim" / "results"


async def list_users() -> list[dict]:
    async with db() as s:
        rows = await s.execute(
            select(User, func.count(ConversationSession.id))
            .join(ConversationSession, ConversationSession.user_id == User.id, isouter=True)
            .group_by(User.id)
            .order_by(User.is_simulated, User.created_at.desc())
        )
        return [
            {
                "id": u.id,
                "name": u.name,
                "native_language": u.native_language,
                "is_simulated": u.is_simulated,
                "level": u.estimated_cefr,
                "sessions": n,
            }
            for u, n in rows
            if n > 0
        ]


async def user_progress(user_id: str) -> dict | None:
    err_min = get_settings().recast_min_confidence
    async with db() as s:
        user = await s.get(User, user_id)
        if user is None:
            return None
        sessions = list(
            (
                await s.execute(
                    select(ConversationSession)
                    .where(ConversationSession.user_id == user_id)
                    .order_by(ConversationSession.started_at)
                )
            ).scalars()
        )
        sess_index = {x.id: i for i, x in enumerate(sessions)}
        obs = list(
            (
                await s.execute(
                    select(Observation, Turn.session_id)
                    .join(Turn, Turn.id == Observation.turn_id)
                    .where(Observation.user_id == user_id)
                    .order_by(Observation.created_at)
                )
            ).all()
        )
        current = {
            r.skill_id: Mastery(r.alpha, r.beta)
            for r in (
                await s.execute(select(SkillMastery).where(SkillMastery.user_id == user_id))
            ).scalars()
        }
        vocab = list(
            (await s.execute(select(VocabItem).where(VocabItem.user_id == user_id))).scalars()
        )
        bench = list(
            (
                await s.execute(
                    select(Turn.text, Turn.session_id)
                    .where(Turn.session_id.in_(sess_index), Turn.benchmark.is_(True))
                    .order_by(Turn.created_at)
                )
            ).all()
        )

    # Replay mastery per session (end-of-session value), same thresholds as the Tutor.
    m: dict[str, Mastery] = defaultdict(Mastery)
    history: dict[str, list[float | None]] = defaultdict(lambda: [None] * len(sessions))
    by_session: dict[int, list[Observation]] = defaultdict(list)
    for o, sid in obs:
        by_session[sess_index[sid]].append(o)
    for i in range(len(sessions)):
        for o in by_session.get(i, []):
            if o.confidence >= (MIN_CONF_CORRECT if o.correct else err_min):
                m[o.skill_id] = m[o.skill_id].update(o.correct, weight=o.confidence)
        for sk, mm in m.items():
            history[sk][i] = round(mm.mean, 3)

    skills = sorted(
        (
            {
                "skill_id": sid,
                "name": SKILL_BY_ID[sid].name if sid in SKILL_BY_ID else sid,
                "area": SKILL_BY_ID[sid].area if sid in SKILL_BY_ID else "other",
                "mastery": round(mm.mean, 3),
                "low": round(max(mm.mean - 1.64 * mm.stdev, 0), 3),
                "high": round(min(mm.mean + 1.64 * mm.stdev, 1), 3),
                "evidence": round(mm.evidence, 1),
                "status": mm.status,
            }
            for sid, mm in current.items()
        ),
        key=lambda x: x["mastery"],
    )

    bench_by_session: dict[str, list[str]] = defaultdict(list)
    for text, sid in bench:
        bench_by_session[sid].append(text)
    benchmarks = [
        {
            "session": sess_index[sid] + 1,
            "date": sessions[sess_index[sid]].started_at,
            "text": " ".join(texts),
            "metrics": sessions[sess_index[sid]].metrics,
        }
        for sid, texts in bench_by_session.items()
    ]

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "native_language": user.native_language,
            "is_simulated": user.is_simulated,
            "level": user.estimated_cefr,
            "persona": user.persona,
        },
        "sessions": [
            {
                "n": i + 1,
                "id": x.id,
                "started_at": x.started_at,
                "metrics": x.metrics,
                "recap": x.recap,
                "summary": x.summary,
                "targets": (x.plan or {}).get("target_skills", []),
                "rationale": (x.plan or {}).get("rationale"),
            }
            for i, x in enumerate(sessions)
        ],
        "skills": skills,
        "skill_history": dict(history),
        "vocab": [
            {
                "word": v.word,
                "status": v.status,
                "times_used": v.times_used,
                "meaning": WORD_BY_KEY[v.word].gloss if v.word in WORD_BY_KEY else None,
            }
            for v in vocab
        ],
        "benchmarks": benchmarks[:1] + benchmarks[-1:] if len(benchmarks) > 1 else benchmarks,
    }


def eval_results() -> dict:
    """Simulation scores, without the full transcripts."""
    out = {}
    for f in sorted(SIM_RESULTS.glob("*.json")):
        d = json.loads(f.read_text())
        out[d["tag"]] = {
            "planner": d["planner"],
            "sessions": d["sessions"],
            "turns": d["turns"],
            "learners": {
                uid: {
                    "name": L["persona"]["name"],
                    "level": L["persona"]["level"],
                    "l1": L["persona"]["l1"],
                    "planted": L["persona"]["error_rates"],
                    "score": L["score"],
                    "true_rates": [s["rates_before"] for s in L["sessions"]],
                    "targets": [s["plan"].get("target_skills", []) for s in L["sessions"]],
                    "metrics": [s["metrics"] for s in L["sessions"]],
                }
                for uid, L in d["learners"].items()
            },
        }
    return out
