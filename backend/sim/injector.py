"""Plants learner errors into correct English with known rates, and logs ground truth.

Why rules and not "LLM, please make 60% article errors": LLMs can't hold an error rate,
and they make the errors you didn't ask for. Rules give exact ground truth, so the
Analyst's precision and recall can be measured rather than eyeballed."""

import random
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass
class Injection:
    skill_id: str
    original: str  # the correct form (what a recast should echo back)
    corrupted: str


Rule = Callable[[str, float, random.Random], tuple[str, list[Injection]]]

IRREGULAR_PAST = {
    "went": "go", "gave": "give", "bought": "buy", "saw": "see", "came": "come", "told": "tell",
    "took": "take", "made": "make", "got": "get", "ate": "eat", "met": "meet", "felt": "feel",
    "thought": "think", "left": "leave", "found": "find", "said": "say", "began": "begin",
    "wrote": "write", "spent": "spend", "drove": "drive", "brought": "bring", "sent": "send",
}  # fmt: skip
REGULAR_PAST = {
    "watched": "watch", "played": "play", "started": "start", "worked": "work",
    "visited": "visit", "talked": "talk", "called": "call", "finished": "finish",
    "wanted": "want", "liked": "like", "enjoyed": "enjoy", "decided": "decide",
    "tried": "try", "cooked": "cook", "stayed": "stay", "planned": "plan", "moved": "move",
}  # fmt: skip
OVERREGULARISED = {
    "went": "goed", "bought": "buyed", "ate": "eated", "caught": "catched",
    "taught": "teached", "thought": "thinked", "brought": "bringed", "felt": "feeled",
    "came": "comed", "made": "maked", "spent": "spended", "told": "telled",
}  # fmt: skip
THIRD_PERSON = {
    "goes": "go", "works": "work", "lives": "live", "likes": "like", "wants": "want",
    "has": "have", "does": "do", "says": "say", "loves": "love", "needs": "need",
    "makes": "make", "takes": "take", "comes": "come", "thinks": "think", "plays": "play",
}  # fmt: skip
STATIVE = {
    "I know": "I am knowing", "I want": "I am wanting", "I like": "I am liking",
    "I understand": "I am understanding", "I believe": "I am believing",
    "I need": "I am needing", "I love": "I am loving",
}  # fmt: skip
UNCOUNTABLE = ["advice", "information", "furniture", "luggage", "equipment", "homework",
               "feedback", "knowledge", "news", "research", "traffic"]  # fmt: skip
PRESENT_PERFECT = {
    "I have been to": "I went to", "I have never": "I never", "I have seen": "I saw",
    "I have visited": "I visited", "I have tried": "I tried", "I've been to": "I went to",
    "I've never": "I never", "I have lived": "I am living", "I have worked": "I am working",
    "I've lived": "I am living", "I've worked": "I am working", "I have known": "I am knowing",
}  # fmt: skip
DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"


def _sub_each(
    text: str,
    pattern: str,
    repl: Callable[[re.Match], str],
    p: float,
    rng: random.Random,
    skill: str,
    flags: int = re.IGNORECASE,
) -> tuple[str, list[Injection]]:
    injected: list[Injection] = []

    def _r(m: re.Match) -> str:
        if rng.random() >= p:
            return m.group(0)
        new = repl(m)
        if new != m.group(0):
            injected.append(Injection(skill, m.group(0), new))
        return new

    return re.sub(pattern, _r, text, flags=flags), injected


def _keep_case(src: str, new: str) -> str:
    return new[0].upper() + new[1:] if src[:1].isupper() else new


def articles(t, p, rng):
    # Drop an article before a noun phrase. Skip "a lot", "a bit", "a few", "the same".
    return _sub_each(
        t,
        r"\b(a|an|the)\s+(?!lot\b|bit\b|few\b|little\b|same\b|most\b)([a-z]+)",
        lambda m: m.group(2),
        p,
        rng,
        "articles",
    )


def past_simple(t, p, rng):
    table = IRREGULAR_PAST | REGULAR_PAST
    return _sub_each(
        t, r"\b(" + "|".join(table) + r")\b",
        lambda m: _keep_case(m.group(1), table[m.group(1).lower()]), p, rng, "past_simple",
    )  # fmt: skip


def past_irregular(t, p, rng):
    return _sub_each(
        t, r"\b(" + "|".join(OVERREGULARISED) + r")\b",
        lambda m: _keep_case(m.group(1), OVERREGULARISED[m.group(1).lower()]), p, rng,
        "past_irregular",
    )  # fmt: skip


def sv_agreement(t, p, rng):
    return _sub_each(
        t, r"\b(he|she|it|my (?:mother|father|brother|sister|wife|husband|friend|manager|boss))\s+("
        + "|".join(THIRD_PERSON) + r")\b",
        lambda m: f"{m.group(1)} {THIRD_PERSON[m.group(2).lower()]}", p, rng, "sv_agreement",
    )  # fmt: skip


def stative_continuous(t, p, rng):
    return _sub_each(
        t, r"\b(" + "|".join(STATIVE) + r")\b(?!\s+(?:to|it was|that it was))",
        lambda m: STATIVE[next(k for k in STATIVE if k.lower() == m.group(1).lower())], p, rng,
        "stative_continuous",
    )  # fmt: skip


def countable_uncountable(t, p, rng):
    return _sub_each(
        t, r"\b(" + "|".join(UNCOUNTABLE) + r")\b(?!s)",
        lambda m: m.group(1) + ("es" if m.group(1).endswith("s") else "s"), p, rng,
        "countable_uncountable",
    )  # fmt: skip


def present_perfect(t, p, rng):
    return _sub_each(
        t, r"\b(" + "|".join(re.escape(k) for k in PRESENT_PERFECT) + r")\b",
        lambda m: PRESENT_PERFECT[next(k for k in PRESENT_PERFECT if k.lower() == m.group(1).lower())],
        p, rng, "present_perfect",
    )  # fmt: skip


def prepositions_time_place(t, p, rng):
    def repl(m):
        w = m.group(0).lower()
        if w.startswith("on ") and re.match(rf"on ({DAYS.lower()})", w):
            return "in " + m.group(0)[3:]
        return {"at night": "in night", "at home": "in home", "on the weekend": "in weekend",
                "at the weekend": "in weekend", "on weekends": "in weekends",
                "in the morning": "on morning", "at work": "in work"}.get(w, m.group(0))  # fmt: skip

    return _sub_each(
        t,
        rf"\b(on (?:{DAYS})|at night|at home|on the weekend|at the weekend|on weekends|"
        r"in the morning|at work)\b",
        repl, p, rng, "prepositions_time_place",
    )  # fmt: skip


def plurals(t, p, rng):
    return _sub_each(
        t,
        r"\b(two|three|four|five|many|several|few|some|all my|so many)\s+([a-z]{3,}?)s\b",
        lambda m: f"{m.group(1)} {m.group(2)}",
        p,
        rng,
        "plurals",
    )


def question_formation(t, p, rng):
    return _sub_each(
        t,
        r"\b(what|where|when|why|how)\s+(do|did|does)\s+(you|they|he|she)\b",
        lambda m: f"{m.group(1)} {m.group(3)}",
        p,
        rng,
        "question_formation",
    )


RULES: dict[str, Rule] = {
    "articles": articles,
    "past_simple": past_simple,
    "past_irregular": past_irregular,
    "sv_agreement": sv_agreement,
    "stative_continuous": stative_continuous,
    "countable_uncountable": countable_uncountable,
    "present_perfect": present_perfect,
    "prepositions_time_place": prepositions_time_place,
    "plurals": plurals,
    "question_formation": question_formation,
}

# Order matters: tense rules first, so "went" isn't both de-tensed and over-regularised.
_ORDER = ["present_perfect", "past_irregular", "past_simple", "stative_continuous",
          "sv_agreement", "countable_uncountable", "plurals", "prepositions_time_place",
          "question_formation", "articles"]  # fmt: skip


def inject(text: str, rates: dict[str, float], rng: random.Random) -> tuple[str, list[Injection]]:
    out: list[Injection] = []
    for skill in _ORDER:
        p = rates.get(skill, 0.0)
        if p <= 0:
            continue
        text, inj = RULES[skill](text, p, rng)
        out += inj
    return text, out
