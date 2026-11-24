"""Run simulated learners through the real Friend + Tutor pipeline and score it.

    uv run python -m sim.run --personas sim-rahul --sessions 8 --turns 6
    uv run python -m sim.run --planner random --tag control     # A/B baseline

Writes sim/results/<tag>.json, which the dashboard and the report read."""

import argparse
import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from sqlalchemy import delete, select

from sim.injector import inject
from sim.personas import PERSONAS, Persona
from voisai import clock, llm
from voisai.agent import lifecycle
from voisai.agent.textchat import run_text_call
from voisai.db.models import ConversationSession as Sess
from voisai.db.models import Memory, Observation, SkillMastery, Turn, User, VocabItem
from voisai.db.session import db, init_db
from voisai.tutor import planner
from voisai.tutor.guard import teacher_leak
from voisai.tutor.skills import SKILL_BY_ID
from voisai.tutor.wordbank import WORD_BY_KEY, used_in

log = logging.getLogger("sim")
RESULTS = Path(__file__).parent / "results"

TARGETED_DECAY = 0.75  # assumed effect of a session spent eliciting + recasting a skill
BACKGROUND_DECAY = 0.97
WORD_ADOPTION_P = 0.4
# Free tiers are per-minute budgets (Groq: 8k tokens/min for the Friend model). A real learner
# takes several seconds per turn; the simulator would otherwise fire them back to back.
MIN_TURN_GAP_S = float(os.environ.get("SIM_TURN_GAP_S", "9"))


@dataclass
class LearnerState:
    rates: dict[str, float]
    words_heard: list[str] = field(default_factory=list)
    words_adopted: list[str] = field(default_factory=list)


@dataclass
class TurnLog:
    clean: str
    spoken: str
    injected: list[dict]
    reply: str = ""
    adopted_word: str | None = None


@dataclass
class SessionLog:
    n: int
    plan: dict
    rates_before: dict
    turns: list[TurnLog] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    opener: str = ""


async def learner_line(p: Persona, history: list[tuple[str, str]], word: str | None) -> str:
    convo = "\n".join(f"{'Maya' if r == 'assistant' else p.name}: {t}" for r, t in history[-8:])
    use = f' If it fits naturally, use the expression "{word}".' if word else ""
    sys = (
        f"You are {p.name}. {p.bio} Style: {p.style}. You are on a casual voice call with your "
        f"friend Maya. Reply to her last message as {p.name} in 1-3 sentences, in CORRECT, simple "
        f"everyday English (no slang, no emojis). Talk about your real life, share details, "
        f"sometimes mention things happening this week or past events.{use} "
        "Output only the words you say."
    )
    out = await llm.chat(
        "sim",
        [{"role": "system", "content": sys}, {"role": "user", "content": convo or "(Maya calls)"}],
        temperature=0.9,
    )
    return re.sub(rf"^{p.name}:\s*", "", out.strip().strip('"'))


async def reset_user(user_id: str) -> None:
    async with db() as s:
        sids = select(Sess.id).where(Sess.user_id == user_id)
        tids = select(Turn.id).where(Turn.session_id.in_(sids))
        await s.execute(delete(Observation).where(Observation.turn_id.in_(tids)))
        await s.execute(delete(Turn).where(Turn.session_id.in_(sids)))
        for m in (Sess, SkillMastery, VocabItem, Memory):
            await s.execute(delete(m).where(m.user_id == user_id))
        await s.execute(delete(User).where(User.id == user_id))


async def create_user(p: Persona, user_id: str) -> None:
    async with db() as s:
        s.add(
            User(
                id=user_id,
                name=p.name,
                native_language=p.l1,
                is_simulated=True,
                persona={"error_rates": p.error_rates, "level": p.level, "bio": p.bio},
            )
        )


def _random_planner():
    original = planner.plan_session

    async def plan(user_id, now=None):
        plan = await original(user_id, now)
        pool = [s.id for s in SKILL_BY_ID.values() if s.area == "grammar"]
        plan.target_skills = random.sample(pool, 2)
        plan.rationale = "control: random targets"
        return plan

    return plan


async def simulate(
    p: Persona, user_id: str, sessions: int, turns: int, seed: int
) -> list[SessionLog]:
    rng = random.Random(seed)
    state = LearnerState(rates=dict(p.error_rates))
    logs: list[SessionLog] = []
    for n in range(1, sessions + 1):
        word_pool = [w for w in state.words_heard if w not in state.words_adopted]
        slog = SessionLog(
            n=n, plan={}, rates_before={k: round(v, 3) for k, v in state.rates.items()}
        )
        pending: list[TurnLog] = []

        last = [0.0]

        async def next_user(history, slog=slog, pending=pending, word_pool=word_pool, last=last):
            if (wait := last[0] + MIN_TURN_GAP_S - time.monotonic()) > 0:
                await asyncio.sleep(wait)
            last[0] = time.monotonic()
            if pending and history and history[-1][0] == "assistant":
                pending[-1].reply = history[-1][1]
            if len(pending) >= turns:
                return None
            word = None
            if word_pool and rng.random() < WORD_ADOPTION_P / max(turns / 3, 1):
                word = word_pool.pop(0)
            clean = await learner_line(p, history, word)
            spoken, inj = inject(clean, state.rates, rng)
            adopted = word if word and used_in(clean, WORD_BY_KEY[word]) else None
            if adopted:
                state.words_adopted.append(adopted)
            pending.append(TurnLog(clean, spoken, [asdict(i) for i in inj], adopted_word=adopted))
            return spoken

        t0 = time.perf_counter()
        try:
            tr = await run_text_call(user_id, p.l1, next_user, max_turns=turns + 1, name=p.name)
        except Exception:
            log.exception(
                "%s session %d failed; stopping this learner after %d sessions", p.id, n, n - 1
            )
            break
        if pending and tr.turns and tr.turns[-1][0] == "assistant":
            pending[-1].reply = tr.turns[-1][1]
        if (missing := await _unanalysed_turns(tr.call.session_id)) > 1:
            log.error(
                "%s session %d: %d turns were never analysed (provider quota?). "
                "Stopping this learner; its scores would be meaningless.",
                p.id,
                n,
                missing,
            )
            break
        slog.plan = tr.call.plan.model_dump()
        slog.turns = pending
        slog.metrics = tr.metrics
        slog.opener = next((t for r, t in tr.turns if r == "assistant"), "")
        log.info("%s session %d done in %.0fs: %s", p.id, n, time.perf_counter() - t0, tr.metrics)

        # Learning model (assumed, see module docstring)
        targeted = set(slog.plan.get("target_skills", []))
        for sk in state.rates:
            state.rates[sk] *= TARGETED_DECAY if sk in targeted else BACKGROUND_DECAY
        for w in tr.call.agent.steer.words_said:
            if w not in state.words_heard:
                state.words_heard.append(w)
        logs.append(slog)
        clock.advance(1)
    return logs


async def _unanalysed_turns(session_id: str) -> int:
    async with db() as s:
        rows = await s.execute(
            select(Turn.id).where(
                Turn.session_id == session_id, Turn.role == "user", Turn.analysis_ms.is_(None)
            )
        )
        return len(rows.all())


def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z']+", s.lower()))


async def score(p: Persona, user_id: str, logs: list[SessionLog]) -> dict:
    """Compare stored observations against ground truth, turn by turn."""
    async with db() as s:
        sessions = list(
            (
                await s.execute(
                    select(Sess).where(Sess.user_id == user_id).order_by(Sess.started_at)
                )
            ).scalars()
        )
        per_skill: dict[str, dict[str, int]] = {}
        leaks, replies, recasts, recast_opps, modeled = [], 0, 0, 0, 0
        for sess, slog in zip(sessions, logs, strict=False):
            uturns = list(
                (
                    await s.execute(
                        select(Turn)
                        .where(Turn.session_id == sess.id, Turn.role == "user")
                        .order_by(Turn.idx)
                    )
                ).scalars()
            )
            later = [f" {_norm(t.reply)} " for t in slog.turns]
            for k, (ut, tl) in enumerate(zip(uturns, slog.turns, strict=False)):
                obs = list(
                    (
                        await s.execute(
                            select(Observation).where(
                                Observation.turn_id == ut.id, Observation.correct.is_(False)
                            )
                        )
                    ).scalars()
                )
                truth: dict[str, int] = {}
                for i in tl.injected:
                    truth[i["skill_id"]] = truth.get(i["skill_id"], 0) + 1
                flagged: dict[str, int] = {}
                for o in obs:
                    flagged[o.skill_id] = flagged.get(o.skill_id, 0) + 1
                for sk in set(truth) | set(flagged):
                    d = per_skill.setdefault(sk, {"tp": 0, "fp": 0, "fn": 0})
                    tp = min(truth.get(sk, 0), flagged.get(sk, 0))
                    d["tp"] += tp
                    d["fp"] += flagged.get(sk, 0) - tp
                    d["fn"] += truth.get(sk, 0) - tp
                if tl.reply:
                    replies += 1
                    if leak := teacher_leak(tl.reply):
                        leaks.append({"reply": tl.reply, "match": leak})
                    reply = f" {_norm(tl.reply)} "
                    for i in tl.injected:
                        if i["skill_id"] == "articles":
                            continue  # "the market" echoes are too common to count as recasts
                        recast_opps += 1
                        target = f" {_norm(i['original'])} "
                        recasts += target in reply
                        # delayed modelling: the Friend uses the correct form within 2 replies
                        modeled += any(target in r for r in later[k : k + 3])

    def prf(d):
        prec = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else None
        rec = d["tp"] / (d["tp"] + d["fn"]) if d["tp"] + d["fn"] else None
        return {**d, "precision": prec and round(prec, 3), "recall": rec and round(rec, 3)}

    tot = {k: sum(d[k] for d in per_skill.values()) for k in ("tp", "fp", "fn")}
    planted = set(p.error_rates)
    hits = [len(planted & set(sl.plan.get("target_skills", []))) for sl in logs]
    return {
        "analyst": {
            "overall": prf(tot),
            "per_skill": {k: prf(v) for k, v in sorted(per_skill.items())},
        },
        "planner": {
            "sessions_targeting_a_planted_skill": (
                round(sum(h > 0 for h in hits) / len(hits), 3) if hits else None
            ),
            "planted_share_of_targets": round(sum(hits) / (2 * len(hits)), 3) if hits else None,
        },
        "friend": {
            "replies": replies,
            "teacher_leak_rate": round(len(leaks) / replies, 3) if replies else None,
            "leaks": leaks[:5],
            "recast_rate": round(recasts / recast_opps, 3) if recast_opps else None,
            "modeled_within_2_rate": round(modeled / recast_opps, 3) if recast_opps else None,
        },
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--personas", default=",".join(PERSONAS))
    ap.add_argument("--sessions", type=int, default=8)
    ap.add_argument("--turns", type=int, default=6)
    ap.add_argument("--planner", choices=["tutor", "random"], default="tutor")
    ap.add_argument("--tag", default="main")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    for noisy in ("livekit", "httpx", "openai", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    await init_db()
    if a.planner == "random":
        lifecycle.plan_session = _random_planner()
    random.seed(a.seed)

    out = {
        "tag": a.tag,
        "planner": a.planner,
        "sessions": a.sessions,
        "turns": a.turns,
        "learners": {},
    }
    RESULTS.mkdir(exist_ok=True)
    for pid in a.personas.split(","):
        p = PERSONAS[pid]
        user_id = p.id if a.tag == "main" else f"{p.id}-{a.tag}"
        clock.reset()
        clock.advance(-a.sessions)  # sessions end "today"
        await reset_user(user_id)
        await create_user(p, user_id)
        logs = await simulate(p, user_id, a.sessions, a.turns, a.seed)
        out["learners"][user_id] = {
            "persona": asdict(p),
            "score": await score(p, user_id, logs),
            "sessions": [asdict(s) for s in logs],
        }
        (RESULTS / f"{a.tag}.json").write_text(json.dumps(out, indent=1, default=str))
        print(json.dumps(out["learners"][user_id]["score"], indent=1))


if __name__ == "__main__":
    asyncio.run(main())
