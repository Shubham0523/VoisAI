"""Tutor pipeline against a real Postgres, with a scripted Analyst (no LLM, no network).
Skipped automatically when the database isn't running (`make db`)."""

import asyncio
import uuid

import pytest

from voisai import clock
from voisai.agent.recorder import Recorder
from voisai.api.progress import user_progress
from voisai.db.models import SkillMastery
from voisai.db.session import db, init_db
from voisai.tutor import service
from voisai.tutor.analyst import MemoryItem, SkillEvidence, TurnAnalysis
from voisai.tutor.planner import plan_session
from voisai.tutor.session_end import finalize_session


def _db_up() -> bool:
    async def ping():
        from voisai.db.session import engine

        try:
            await init_db()
        finally:
            await engine.dispose()  # pooled connections are bound to this throwaway loop

    try:
        asyncio.run(asyncio.wait_for(ping(), 5))
        return True
    except Exception:  # noqa: BLE001 - any failure means 'no database', so skip
        return False


pytestmark = pytest.mark.skipif(not _db_up(), reason="Postgres not running (make db)")


def ev(skill, correct, span="x", fix=None, conf=0.95):
    return SkillEvidence(
        skill_id=skill, correct=correct, span=span, correction=fix, confidence=conf
    )


@pytest.fixture
async def user():
    from voisai.db.session import engine

    uid = f"test-{uuid.uuid4().hex[:8]}"
    clock.reset()
    yield uid
    clock.reset()
    from sim.run import reset_user

    await reset_user(uid)
    await engine.dispose()


async def _session(
    uid: str, turns: list[tuple[str, TurnAnalysis]], introduced=frozenset(), friend=""
):
    sid = str(uuid.uuid4())
    plan = await plan_session(uid)
    rec = Recorder(uid, sid)
    await rec.start(plan.model_dump())
    for text, analysis in turns:
        tid = await rec.add_turn("user", text)
        await service.apply_analysis(uid, sid, tid, text, analysis, set(introduced), friend)
    metrics = await finalize_session(sid, summarize=False)
    return sid, plan, metrics


async def test_full_tutor_loop(user):
    # Session 1: articles go wrong twice, past tense right once; an interview is coming up.
    _, _, m1 = await _session(
        user,
        [
            (
                "I go to office",
                TurnAnalysis(evidence=[ev("articles", False, "go to office", "go to the office")]),
            ),
            (
                "Yesterday I watched a film and I have interview on Friday",
                TurnAnalysis(
                    evidence=[
                        ev("past_simple", True, "watched"),
                        ev("articles", False, "have interview", "have an interview"),
                        ev("tag_questions", False, "x", "y", conf=0.3),  # below threshold: ignored
                    ],
                    memories=[
                        MemoryItem(
                            text="Has a job interview on Friday", kind="followup", due_in_days=2
                        )
                    ],
                ),
            ),
        ],
    )
    assert m1["errors"] == 2 and m1["user_turns"] == 2

    async with db() as s:
        rows = {
            r.skill_id: r
            for r in (
                await s.execute(SkillMastery.__table__.select().where(SkillMastery.user_id == user))
            ).all()
        }
    assert set(rows) == {"articles", "past_simple"}  # low-confidence evidence never counted

    # Session 2, two days later: the follow-up is due and articles are the top target.
    clock.advance(2)
    _, plan2, _ = await _session(
        user,
        [("It was hectic but fine", TurnAnalysis())],
        introduced={"hectic"},
        friend="How was it?",
    )
    assert plan2.opener and "interview" in plan2.opener
    assert "articles" in plan2.target_skills
    assert plan2.session_number == 2 and plan2.benchmark  # 2nd chat is the first benchmark

    # A word the Friend *just* said doesn't count as uptake.
    _, _, m3 = await _session(
        user, [("So hectic today", TurnAnalysis())], introduced={"hectic"}, friend="hectic day?"
    )
    assert m3["words_used"] == []

    prog = await user_progress(user)
    assert prog is not None
    assert [v["word"] for v in prog["vocab"] if v["status"] == "used"] == ["hectic"]
    # Replayed history ends exactly at the stored belief: the dashboard can't drift from the model.
    stored = {s["skill_id"]: s["mastery"] for s in prog["skills"]}
    replayed = {k: v[-1] for k, v in prog["skill_history"].items()}
    assert stored == replayed
    assert prog["sessions"][0]["recap"]["polish"]["natural"] in {
        "go to the office",
        "have an interview",
    }


async def test_concurrent_turns_keep_all_evidence(user):
    """Two analyses landing at once used to race on creating the same skill row."""
    sid = str(uuid.uuid4())
    rec = Recorder(user, sid)
    await rec.start((await plan_session(user)).model_dump())
    tids = [await rec.add_turn("user", f"turn {i}") for i in range(4)]
    a = TurnAnalysis(evidence=[ev("articles", False, "to office", "to the office")])
    await asyncio.gather(
        *(service.apply_analysis(user, sid, t, "turn", a, set(), "") for t in tids)
    )
    async with db() as s:
        row = await s.get(SkillMastery, (user, "articles"))
    assert row is not None and row.beta > 1 + 3.5  # all four errors counted
