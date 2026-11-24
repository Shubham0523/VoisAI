"""Mastery per skill as a Beta distribution over P(correct in an obligatory context).

Why Beta and not full Bayesian Knowledge Tracing: BKT needs fitted guess/slip/learn
parameters per skill, which we don't have data for. Beta counts are interpretable
("right 7 of the last 9 times it was needed"), give a confidence interval for free
(so the Planner can tell "weak" from "unknown"), and decay lets old evidence fade.
"""

from dataclasses import dataclass
from math import sqrt

PRIOR = (1.0, 1.0)  # uniform; seeded per CEFR level in a later pass
DECAY = 0.97  # per observation: recent evidence counts more than last month's


@dataclass
class Mastery:
    alpha: float = PRIOR[0]
    beta: float = PRIOR[1]

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def evidence(self) -> float:
        return self.alpha + self.beta - sum(PRIOR)

    @property
    def stdev(self) -> float:
        a, b = self.alpha, self.beta
        return sqrt(a * b / ((a + b) ** 2 * (a + b + 1)))

    def update(self, correct: bool, weight: float = 1.0) -> "Mastery":
        """`weight` is the Analyst's confidence, so a shaky detection moves the needle less."""
        a = PRIOR[0] + (self.alpha - PRIOR[0]) * DECAY
        b = PRIOR[1] + (self.beta - PRIOR[1]) * DECAY
        if correct:
            a += weight
        else:
            b += weight
        return Mastery(a, b)

    @property
    def status(self) -> str:
        if self.evidence < 3:
            return "unknown"
        if self.mean >= 0.85:
            return "mastered"
        if self.mean >= 0.6:
            return "developing"
        return "weak"


def priority(m: Mastery, l1_prone: bool, recently_targeted: bool) -> float:
    """Planner score: weak skills with enough evidence first, then uncertain ones worth
    probing. L1-prone skills get a bump; skills targeted last session get a rest."""
    weakness = 1.0 - m.mean
    uncertainty = m.stdev * 2
    score = weakness + 0.5 * uncertainty + (0.15 if l1_prone else 0.0)
    return score * (0.5 if recently_targeted else 1.0)
