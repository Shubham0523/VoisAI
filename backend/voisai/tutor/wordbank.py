"""Target words the Friend can slip into conversation ("slightly above level" input).
Each has a level and a gloss; the gloss is only used on the recap card, never in the call.
Uptake is tracked as: introduced (Friend said it) -> used (learner said it unprompted)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TargetWord:
    word: str
    level: str
    gloss: str
    forms: tuple[str, ...] = ()  # inflections counted as a use


def _w(word: str, level: str, gloss: str, *forms: str) -> TargetWord:
    return TargetWord(word, level, gloss, (word, *forms))


WORDS: list[TargetWord] = [
    # B1
    _w("exhausted", "B1", "extremely tired"),
    _w("convenient", "B1", "easy or suitable for you", "inconvenient"),
    _w("figure out", "B1", "understand or solve", "figured out", "figuring out", "figures out"),
    _w("look forward to", "B1", "feel happy about something coming", "looking forward to"),
    _w("deal with", "B1", "handle a problem", "dealt with", "dealing with"),
    _w("afford", "B1", "have enough money for", "afforded", "affordable"),
    _w("crowded", "B1", "full of people"),
    _w("decent", "B1", "good enough, acceptable"),
    _w("hang out", "B1", "spend relaxed time with friends", "hanging out", "hung out"),
    _w("on the way", "B1", "while travelling somewhere"),
    _w("make sense", "B1", "be logical or understandable", "makes sense", "made sense"),
    _w("worth it", "B1", "good enough to justify the effort or cost"),
    _w("turn out", "B1", "end up being", "turned out", "turns out"),
    _w("get used to", "B1", "become familiar with", "got used to", "getting used to"),
    _w("run out of", "B1", "have none left", "ran out of", "running out of"),
    # B2
    _w("reluctant", "B2", "not wanting to do something", "reluctantly"),
    _w("overwhelmed", "B2", "feeling it's too much to handle", "overwhelming"),
    _w("hectic", "B2", "very busy and full of activity"),
    _w("thrilled", "B2", "extremely pleased", "thrilling"),
    _w("struggle", "B2", "find something very difficult", "struggled", "struggling"),
    _w("tempting", "B2", "making you want to do or have it", "tempted"),
    _w(
        "procrastinate",
        "B2",
        "delay doing something",
        "procrastinating",
        "procrastinated",
        "procrastination",
    ),
    _w("vibe", "B2", "the feeling a place or person gives", "vibes"),
    _w("frustrating", "B2", "annoying because you can't do something", "frustrated"),
    _w("commute", "B2", "the regular journey to work", "commuting", "commuted"),
    _w("cope with", "B2", "manage a difficult situation", "coped with", "coping with"),
    _w("impressive", "B2", "making you admire it", "impressed"),
    _w("bittersweet", "B2", "happy and sad at the same time"),
    _w("burnt out", "B2", "exhausted from too much work", "burnout", "burned out"),
    _w("catch up", "B2", "talk to learn each other's news", "caught up", "catching up"),
    _w("spontaneous", "B2", "done without planning", "spontaneously"),
    _w("nostalgic", "B2", "missing the past fondly", "nostalgia"),
    _w("down to earth", "B2", "practical and humble"),
    _w("game changer", "B2", "something that changes a situation a lot"),
    _w("the bottom line", "B2", "the most important point"),
    # C1
    _w("meticulous", "C1", "very careful about details", "meticulously"),
    _w("resilient", "C1", "able to recover quickly", "resilience"),
    _w("daunting", "C1", "seeming difficult and scary"),
    _w("candid", "C1", "honest and direct", "candidly"),
    _w("ambivalent", "C1", "having mixed feelings"),
    _w("serendipity", "C1", "a happy accident", "serendipitous"),
    _w("on the fence", "C1", "unable to decide"),
    _w("a blessing in disguise", "C1", "something bad that turns out good"),
]

WORD_BY_KEY = {w.word: w for w in WORDS}
_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


def next_level(level: str | None) -> str:
    """i+1: one band above the learner's current estimate."""
    if level not in _LEVELS:
        return "B1"
    return _LEVELS[min(_LEVELS.index(level) + 1, len(_LEVELS) - 2)]


def used_in(text: str, w: TargetWord) -> bool:
    t = f" {_norm(text)} "
    return any(f" {_norm(f)} " in t for f in w.forms)


def _norm(s: str) -> str:
    return " ".join("".join(c.lower() if c.isalnum() else " " for c in s).split())
