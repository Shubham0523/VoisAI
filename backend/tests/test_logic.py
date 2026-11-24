from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from voisai.llm import parse_json
from voisai.tutor import metrics
from voisai.tutor.guard import teacher_leak
from voisai.tutor.learner_model import Mastery
from voisai.tutor.planner import SessionPlan, Steer, rank_skills
from voisai.tutor.session_end import build_recap
from voisai.tutor.skills import SKILL_BY_ID
from voisai.tutor.wordbank import WORD_BY_KEY, next_level, used_in


# --- Planner
def test_rank_prefers_weak_with_evidence_over_mastered():
    weak = Mastery()
    for _ in range(6):
        weak = weak.update(False)
    strong = Mastery()
    for _ in range(40):
        strong = strong.update(True)
    ranked = dict(rank_skills({"articles": weak, "past_simple": strong}, "Hindi", "B1", set()))
    assert "past_simple" not in ranked  # mastered skills are skipped
    assert max(ranked, key=ranked.get) == "articles"


def test_rank_respects_level_cap():
    ids = {sid for sid, _ in rank_skills({}, "Hindi", "A2", set())}
    assert "idioms" not in ids  # C1 skill is too far above an A2 learner
    assert "past_simple" in ids


def test_rank_rests_recently_targeted():
    a = dict(rank_skills({}, "Hindi", "B1", set()))["articles"]
    b = dict(rank_skills({}, "Hindi", "B1", {"articles"}))["articles"]
    assert b < a


def test_steer_hints_never_name_grammar():
    plan = SessionPlan(
        target_skills=["past_simple", "articles"], target_words=["hectic"], benchmark=True
    )
    st = Steer(plan)
    hints = [st.next_hint() for _ in range(8)]
    assert hints[0] is None  # let the first exchange breathe
    joined = " ".join(h for h in hints if h)
    for skill in plan.target_skills:
        assert skill not in joined
        assert SKILL_BY_ID[skill].name not in joined
    assert "trip" in joined  # benchmark asked once
    assert joined.count("trip or a day out") == 1


def test_steer_benchmark_flags_next_user_turn():
    st = Steer(SessionPlan(benchmark=True))
    st.next_hint(), st.next_hint()
    assert st.next_hint() is not None and st.awaiting_benchmark_answer
    st.next_hint()
    assert not st.awaiting_benchmark_answer


def test_steer_stops_pushing_word_once_said():
    st = Steer(SessionPlan(target_words=["hectic", "thrilled"]))
    st.next_hint()
    assert "hectic" in st.next_hint()
    assert st.observe_assistant("Sounds like a hectic week!") == ["hectic"]
    assert "thrilled" in st.next_hint()


def test_steer_adds_repeated_error_skill():
    st = Steer(SessionPlan(target_skills=["articles"]))
    st.observe_errors([("past_simple", "I go", "I went"), ("past_simple", "he give", "he gave")])
    assert "past_simple" in st._skills()


def test_steer_models_latest_short_correction_once():
    st = Steer(SessionPlan())
    st.next_hint()
    st.observe_errors([("past_simple", "Yesterday I go", "Yesterday I went")])
    h = st.next_hint()
    assert '"Yesterday I went"' in h and "past" not in h.lower()
    assert st.next_hint() is None


# --- Guard
@pytest.mark.parametrize(
    "text",
    [
        'You said "I go", but we usually say "I went".',
        "Small correction: it's past tense here.",
        "Your English is really good!",
        "The correct form is 'went'.",
    ],
)
def test_guard_catches_teaching(text):
    assert teacher_leak(text)


@pytest.mark.parametrize(
    "text",
    [
        "Oh, your manager gave you a new project yesterday? What's it about?",
        "That sounds hectic! How did you deal with it?",
        "So you went to Goa last week, how was the weather?",
    ],
)
def test_guard_allows_recasts(text):
    assert teacher_leak(text) is None


# --- Words
def test_word_forms_and_boundaries():
    assert used_in("I figured out the bug finally", WORD_BY_KEY["figure out"])
    assert used_in("Work was so HECTIC.", WORD_BY_KEY["hectic"])
    assert not used_in("hecticness", WORD_BY_KEY["hectic"])
    assert next_level("B1") == "B2" and next_level(None) == "B1"


# --- Metrics
def test_mattr_is_length_robust():
    short = [
        "i",
        "went",
        "to",
        "the",
        "market",
        "and",
        "bought",
        "apples",
        "and",
        "then",
        "i",
        "came",
        "home",
    ]
    assert metrics.mattr(short) is not None
    rep = ("the cat sat on the mat " * 20).split()
    varied = " ".join(f"w{i}" for i in range(120)).split()
    assert metrics.mattr(varied) > metrics.mattr(rep)


def test_tokens_drop_fillers():
    assert metrics.tokens("Um, I uh went there") == ["i", "went", "there"]


def test_cefr_needs_evidence_then_tracks_mastery():
    assert metrics.estimate_cefr({"past_simple": Mastery(3, 1)}, None) is None
    good = Mastery(9, 1)
    bad = Mastery(1, 9)
    rows = {"past_simple": good, "sv_agreement": good, "articles": good, "present_perfect": bad}
    assert metrics.estimate_cefr(rows, None) in {"A2", "B1"}
    rows["present_perfect"] = good
    rows["conditionals_2"] = good
    assert metrics.estimate_cefr(rows, None) == "B1"


# --- Recap
def _obs(skill, correct, span="x", fix=None, conf=0.9):
    return SimpleNamespace(
        skill_id=skill, correct=correct, span=span, correction=fix, confidence=conf
    )


def test_recap_uses_only_confident_real_errors():
    errs = [_obs("past_simple", False, "I go yesterday", "I went yesterday", 0.95),
            _obs("articles", False, "go to office", "go to the office", 0.7)]  # fmt: skip
    obs = [*errs, _obs("plurals", True), _obs("plurals", True)]
    card = build_recap(errs, obs, ["hectic"], [])
    assert card["polish"]["natural"] == "I went yesterday"
    assert card["win"]["skill"] == SKILL_BY_ID["plurals"].name
    assert card["word"] == {
        "word": "hectic",
        "meaning": WORD_BY_KEY["hectic"].gloss,
        "you_used_it": True,
    }
    assert build_recap([], [], [], []) is None


# --- LLM output parsing
class _S(BaseModel):
    a: int


def test_parse_json_tolerates_fences_and_think():
    assert parse_json('{"a": 1}', _S).a == 1
    assert parse_json('<think>hmm</think>\n```json\n{"a": 2}\n```', _S).a == 2
    with pytest.raises(ValueError):
        parse_json("no json here", _S)


# --- Analyst normalisation
def _ev(skill, span, fix, correct=False):
    from voisai.tutor.analyst import SkillEvidence

    return SkillEvidence(skill_id=skill, correct=correct, span=span, correction=fix, confidence=0.9)


def test_normalize_relabels_dedupes_and_drops():
    from voisai.tutor.analyst import normalize

    out = normalize(
        [
            _ev("past_simple", "ended in tight contest", "ended in a tight contest"),
            _ev("articles", "in tight contest", "in a tight contest"),  # duplicate of the above
            _ev("future_forms", "flatmates in Sunday", "flatmates on Sunday"),
            _ev("past_simple", "I had two calls", "I got two calls"),  # style, already past
            _ev("past_simple", "I decide to try", "I decided to try"),
            _ev("past_simple", "My day was busy", "My day was busy (Note: correct)"),
            _ev("word_choice", "it was nice", "it was nice"),
            _ev("not_a_skill", "x", "y"),
            _ev("plurals", "two friends", None, correct=True),
        ]
    )
    got = [(e.skill_id, e.correct) for e in out]
    assert got == [
        ("articles", False),
        ("prepositions_time_place", False),
        ("past_simple", False),
        ("plurals", True),
    ]


def test_database_url_from_hosted_provider():
    from voisai.config import Settings

    url = Settings(
        database_url="postgres://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require"
    ).database_url
    assert url == "postgresql+asyncpg://u:p@ep-x.neon.tech/db?ssl=require"
    local = "postgresql+asyncpg://voisai:voisai@localhost:5433/voisai"
    assert Settings(database_url=local).database_url == local
