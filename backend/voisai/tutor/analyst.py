"""Analyst: tags each user turn against the skill list. Runs off the hot path
(after the Friend has already started replying), so it can use a slower, smarter model."""

import difflib
import logging
import re

from pydantic import BaseModel, Field

from voisai import clock, llm
from voisai.tutor.skills import SKILL_BY_ID, skill_menu

log = logging.getLogger("voisai.analyst")


class SkillEvidence(BaseModel):
    skill_id: str = Field(description="id from the skill list")
    correct: bool = Field(description="true if used correctly where the context required it")
    span: str = Field(description="exact words the learner said")
    correction: str | None = Field(None, description="what a fluent speaker would say, if wrong")
    confidence: float = Field(0.8, ge=0, le=1, description="how sure you are")


class MemoryItem(BaseModel):
    text: str = Field(description="one fact, written in third person, e.g. 'Has a job interview'")
    kind: str = Field("fact", description="fact | event | preference | followup")
    due_in_days: int | None = Field(
        None, description="for followup: days from now when it is worth asking about it"
    )


class TurnAnalysis(BaseModel):
    evidence: list[SkillEvidence] = Field(default_factory=list)
    memories: list[MemoryItem] = Field(default_factory=list)


SYSTEM_PROMPT = """You are a meticulous applied linguist analysing ONE spoken turn from an
English learner (native language: {l1}). The text is a verbatim speech transcript:
- ignore punctuation and capitalisation, and do NOT treat um/uh or repeated words as errors;
- widely understood Indian English is fine unless it would confuse an international listener.

Task 1, evidence. For each skill below that this turn gives clear evidence for, add one item:
- correct=false only when a fluent speaker would definitely not say it. Give the corrected phrase.
- correct=true when the learner correctly produced the skill in a context that required it
  (e.g. a correct past-tense verb about yesterday). Record at most 4 correct items, choosing the
  most informative ones.
- One item per distinct error. Use only skill ids from the list. Short turns usually have 0-3 items.
- File each error under the skill that is actually broken: a missing "a/an/the" is ALWAYS
  "articles", whatever the tense. Never file one error under two skills.
- Natural Indian English is not an error: "I am working as a tester", "I am from Pune",
  "my good name" style politeness, "na" or "yaar" tags.
- confidence: 0.9+ only for unambiguous errors.

Task 2, memories. Facts a caring friend would remember (job, family, plans, likes, worries).
Upcoming events (interview Friday, trip next week) are kind="followup" with due_in_days set.
Return [] if nothing new.

Skills:
{skills}
"""


EXAMPLE = """{"evidence": [
  {"skill_id": "past_simple", "correct": false, "span": "Yesterday I go", "correction": "Yesterday I went", "confidence": 0.95},
  {"skill_id": "plurals", "correct": true, "span": "two friends", "correction": null, "confidence": 0.8}
 ],
 "memories": [{"text": "Has a job interview", "kind": "followup", "due_in_days": 3}]}"""


async def analyze_turn(user_text: str, prev_assistant_text: str, l1: str) -> TurnAnalysis:
    if len(user_text.split()) < 2:
        return TurnAnalysis()
    today = clock.now().strftime("%A %d %B %Y")
    user = f'Today is {today}.\nFriend said: "{prev_assistant_text}"\nLearner said: "{user_text}"'
    result = await llm.structured(
        "analyst",
        SYSTEM_PROMPT.format(l1=l1, skills=skill_menu()),
        user,
        TurnAnalysis,
        example=EXAMPLE,
    )
    result.evidence = normalize(result.evidence)
    return result


ARTICLES = {"a", "an", "the"}
PREPOSITIONS = {"in", "on", "at"}
PAST_FORMS = {
    "was", "were", "had", "did", "went", "gave", "got", "made", "came", "saw", "took",
    "told", "said", "felt", "thought", "bought", "left", "met", "ate", "found", "began",
}  # fmt: skip
MAX_CHANGED_TOKENS = 4


def _toks(s: str) -> list[str]:
    return re.findall(r"[a-z']+", s.lower())


def _diff(span: str, fix: str) -> tuple[list[str], list[str]]:
    """Tokens removed from the span and tokens added by the correction."""
    a, b = _toks(span), _toks(fix)
    removed, added = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        if op != "equal":
            removed += a[i1:i2]
            added += b[j1:j2]
    return removed, added


def normalize(evidence: list[SkillEvidence]) -> list[SkillEvidence]:
    """LLM detects, rules normalise. Small models misfile errors (a missing article tagged
    as a tense error), double-count one error under two skills, and emit stylistic rewrites
    as "errors". A word-level diff of span vs correction fixes most of that cheaply."""
    out: list[SkillEvidence] = []
    seen: set[tuple[str, str]] = set()
    for e in evidence:
        if e.skill_id not in SKILL_BY_ID:
            log.debug("dropping unknown skill id %s", e.skill_id)
            continue
        if e.correct:
            out.append(e)
            continue
        if not e.correction:
            continue
        removed, added = _diff(e.span, e.correction)
        changed = set(removed) | set(added)
        if not changed:
            continue  # "correction" identical to what they said
        if len(removed) + len(added) > MAX_CHANGED_TOKENS or "(" in e.correction:
            continue  # a rewrite or a note, not a pinpointed error
        if changed <= ARTICLES:
            e.skill_id = "articles"
        elif changed <= PREPOSITIONS:
            e.skill_id = "prepositions_time_place"
        elif (
            e.skill_id == "past_simple"
            and removed
            and all(t in PAST_FORMS or t.endswith("ed") for t in removed)
        ):
            continue  # already past tense: a style change ("had" -> "got"), not an error
        key = (e.skill_id, " ".join(sorted(changed)))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out
