"""Detects the Friend breaking character into teacher mode. Used as an eval metric in the
simulated-learner runs and in tests; a production version would also sample live calls."""

import re

_PATTERNS = [
    r"\byou said\b[^.?!]*\b(but|instead)\b",
    r"\bwe (usually|normally|would) say\b",
    r"\b(should|could) say\b",
    r"\binstead of (saying )?[\"'“]",
    r"\b(grammar|grammatical(ly)?|tense|correction|corrected)\b",
    r"\bthe (right|correct|proper) (word|way|form)\b",
    r"\b(your|good) english\b",
    r"\bsmall (tip|correction)\b",
]
_RX = re.compile("|".join(_PATTERNS), re.IGNORECASE)


def teacher_leak(text: str) -> str | None:
    """Returns the matched phrase if the Friend sounded like a teacher, else None."""
    m = _RX.search(text)
    return m.group(0) if m else None
