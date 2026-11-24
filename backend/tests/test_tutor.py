from voisai.tutor import fluency
from voisai.tutor.learner_model import Mastery
from voisai.tutor.skills import SKILL_BY_ID, SKILLS


def test_skill_ids_unique():
    assert len(SKILL_BY_ID) == len(SKILLS) >= 35


def test_mastery_moves_with_evidence():
    m = Mastery()
    for _ in range(8):
        m = m.update(correct=False)
    assert m.status == "weak"
    for _ in range(40):  # decay means recovery takes sustained correct use
        m = m.update(correct=True)
    assert m.status == "mastered"


def test_low_confidence_moves_less():
    assert Mastery().update(False, 0.3).mean > Mastery().update(False, 1.0).mean


def test_fluency_counts_pauses_and_fillers():
    W = fluency.Word
    words = [
        W("I", 0.0, 0.2),
        W("um", 0.3, 0.5),
        W("went", 1.3, 1.6),
        W("went", 1.7, 1.9),
        W("there", 3.6, 3.9),
        W("yesterday", 4.0, 4.6),
    ]
    m = fluency.compute(words)
    assert m.fillers == 1 and m.repetitions == 1
    assert m.pauses == 2 and m.long_pauses == 1
