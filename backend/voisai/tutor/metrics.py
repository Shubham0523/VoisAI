"""Text metrics for "is the learner actually improving?". Pure functions.

All of these are standard in second-language research (complexity, accuracy, fluency):
- accuracy: errors per 100 words (lower is better), per-skill accuracy in obligatory contexts
- lexical diversity: MATTR (moving-average type-token ratio). Plain TTR falls as speech gets
  longer, which would punish a learner for talking more; MATTR is length-robust.
- complexity: mean length of utterance, share of subordinate-clause markers
"""

import re
from statistics import mean

from voisai.tutor.fluency import FILLERS
from voisai.tutor.learner_model import Mastery
from voisai.tutor.skills import SKILL_BY_ID

_TOKEN = re.compile(r"[a-zA-Z']+")
SUBORDINATORS = {
    "because", "although", "though", "while", "when", "whenever", "if", "unless", "since",
    "which", "who", "whom", "whose", "that", "where", "until", "whereas", "so",
}  # fmt: skip


def tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text) if t.lower() not in FILLERS]


def mattr(toks: list[str], window: int = 25) -> float | None:
    if len(toks) < window:
        return round(len(set(toks)) / len(toks), 3) if len(toks) >= 10 else None
    ratios = [len(set(toks[i : i + window])) / window for i in range(len(toks) - window + 1)]
    return round(mean(ratios), 3)


def complexity(utterances: list[str]) -> dict:
    toks_per = [tokens(u) for u in utterances if u.strip()]
    toks_per = [t for t in toks_per if t]
    if not toks_per:
        return {"mean_utterance_len": None, "subordination_rate": None}
    all_toks = [t for ts in toks_per for t in ts]
    return {
        "mean_utterance_len": round(mean(len(t) for t in toks_per), 1),
        "subordination_rate": round(
            sum(t in SUBORDINATORS for t in all_toks) / len(all_toks) * 100, 1
        ),
    }


_ORDER = ["A2", "B1", "B2", "C1"]


def estimate_cefr(mastery: dict[str, Mastery], diversity: float | None) -> str | None:
    """Transparent heuristic, not a certified test: a band counts as secured when the skills
    expected at that band (with evidence) average >= 0.7 mastery. Lexical diversity can lift
    the estimate by at most one band. Returns None until there is enough evidence."""
    by_band: dict[str, list[float]] = {b: [] for b in _ORDER}
    for sid, m in mastery.items():
        sk = SKILL_BY_ID.get(sid)
        if sk and sk.cefr in by_band and m.evidence >= 2:
            by_band[sk.cefr].append(m.mean)
    if sum(len(v) for v in by_band.values()) < 3:
        return None
    level = "A2"
    for band in _ORDER:
        vals = by_band[band]
        if not vals:
            continue
        if mean(vals) >= 0.7:
            level = band
        else:
            break
    if diversity is not None and diversity >= 0.78 and level in {"A2", "B1"}:
        level = _ORDER[_ORDER.index(level) + 1]
    return level
