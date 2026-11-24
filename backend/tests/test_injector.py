import random

from sim.injector import RULES, inject


def rng():
    return random.Random(0)


def test_each_rule_fires_at_p1_and_never_at_p0():
    samples = {
        "articles": "I bought a new phone at the mall.",
        "past_simple": "Yesterday I went to the office and watched a film.",
        "past_irregular": "I bought some mangoes.",
        "sv_agreement": "My brother works in Dubai and he likes it.",
        "stative_continuous": "I know the answer.",
        "countable_uncountable": "She gave me good advice.",
        "present_perfect": "I have never seen snow.",
        "prepositions_time_place": "I relax at home on Sunday.",
        "plurals": "I have two sisters.",
        "question_formation": "What do you do on weekends?",
    }
    for skill, text in samples.items():
        out, inj = RULES[skill](text, 1.0, rng())
        assert inj and out != text, skill
        assert all(i.skill_id == skill for i in inj)
        same, none = RULES[skill](text, 0.0, rng())
        assert same == text and not none


def test_articles_spares_fixed_phrases():
    out, inj = RULES["articles"]("I like it a lot and a bit more", 1.0, rng())
    assert out == "I like it a lot and a bit more" and not inj


def test_inject_logs_ground_truth_with_originals():
    out, inj = inject(
        "Yesterday I went to the market and bought two mangoes.",
        {"past_simple": 1.0, "articles": 1.0},
        rng(),
    )
    assert out == "Yesterday I go to market and buy two mangoes."
    assert {(i.skill_id, i.original) for i in inj} == {
        ("past_simple", "went"),
        ("past_simple", "bought"),
        ("articles", "the market"),
    }


def test_rates_are_respected_statistically():
    r = random.Random(42)
    n = sum(len(RULES["articles"]("I saw the dog", 0.3, r)[1]) for _ in range(2000))
    assert 500 < n < 700
