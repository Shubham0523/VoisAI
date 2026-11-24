"""Fluency from STT word timings. Pure functions, no LLM: cheap, deterministic, testable."""

from dataclasses import asdict, dataclass
from itertools import pairwise

FILLERS = {"um", "umm", "uh", "uhh", "er", "erm", "hmm", "mm", "ah"}
SOFT_FILLERS = {"like", "basically", "actually", "so"}  # only counted when repeated
PAUSE_S = 0.5  # gap that counts as a hesitation inside an utterance
LONG_PAUSE_S = 1.5


@dataclass
class Word:
    w: str
    start: float
    end: float
    conf: float | None = None


@dataclass
class FluencyMetrics:
    words: int
    speech_seconds: float
    wpm: float  # articulation rate excluding long pauses
    pauses: int
    long_pauses: int
    mean_pause_s: float
    fillers: int
    fillers_per_100w: float
    repetitions: int  # "I I went", a proxy for self-correction
    low_conf_words: int  # candidate pronunciation issues

    def as_dict(self) -> dict:
        return asdict(self)


def _norm(w: str) -> str:
    return w.lower().strip(".,!?;:'\"")


def compute(words: list[Word]) -> FluencyMetrics | None:
    if len(words) < 3:
        return None
    gaps = [b.start - a.end for a, b in pairwise(words)]
    pauses = [g for g in gaps if g >= PAUSE_S]
    long_pauses = [g for g in gaps if g >= LONG_PAUSE_S]
    total = max(words[-1].end - words[0].start, 0.01)
    speaking = max(total - sum(long_pauses), 0.01)

    toks = [_norm(w.w) for w in words]
    fillers = sum(t in FILLERS for t in toks)
    fillers += sum(1 for a, b in pairwise(toks) if a == b and a in SOFT_FILLERS)
    reps = sum(1 for a, b in pairwise(toks) if a == b and a not in FILLERS)
    content = len(toks) - fillers

    return FluencyMetrics(
        words=content,
        speech_seconds=round(total, 2),
        wpm=round(content / speaking * 60, 1),
        pauses=len(pauses),
        long_pauses=len(long_pauses),
        mean_pause_s=round(sum(pauses) / len(pauses), 2) if pauses else 0.0,
        fillers=fillers,
        fillers_per_100w=round(fillers / max(content, 1) * 100, 1),
        repetitions=reps,
        low_conf_words=sum(1 for w in words if w.conf is not None and w.conf < 0.6),
    )
