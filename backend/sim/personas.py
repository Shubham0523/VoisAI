"""Simulated learners. Error rates are per opportunity (e.g. 0.6 = 60% of articles dropped).
Profiles follow well-documented transfer patterns for Indian-language speakers."""

from dataclasses import dataclass, field


@dataclass
class Persona:
    id: str
    name: str
    l1: str
    level: str
    bio: str
    error_rates: dict[str, float]
    style: str = ""
    known_facts: list[str] = field(default_factory=list)


PERSONAS: dict[str, Persona] = {
    p.id: p
    for p in [
        Persona(
            id="sim-rahul",
            name="Rahul",
            l1="Hindi",
            level="B1",
            bio="26, software tester at an IT company in Pune, from Indore. Lives with two "
            "flatmates, plays cricket on Sundays, preparing for job interviews at bigger "
            "companies, misses his mother's cooking.",
            error_rates={
                "articles": 0.6,
                "past_simple": 0.5,
                "stative_continuous": 0.7,
                "prepositions_time_place": 0.5,
            },
            style="friendly, a bit shy, gives medium-length answers",
        ),
        Persona(
            id="sim-priya",
            name="Priya",
            l1="Tamil",
            level="A2",
            bio="34, home baker in Chennai starting to sell cakes on Instagram. Has two "
            "kids, her husband works in a bank, loves Ilaiyaraaja songs and watering her "
            "plants every morning.",
            error_rates={
                "past_simple": 0.6,
                "plurals": 0.5,
                "sv_agreement": 0.6,
                "question_formation": 0.7,
                "articles": 0.4,
            },
            style="warm, enthusiastic, short sentences",
        ),
        Persona(
            id="sim-arjun",
            name="Arjun",
            l1="Hindi",
            level="B2",
            bio="23, MBA student in Delhi doing an internship in marketing. Wants to work in "
            "London, follows football, has been to Goa and Manali, worried about "
            "placements.",
            error_rates={
                "present_perfect": 0.6,
                "countable_uncountable": 0.7,
                "articles": 0.25,
                "past_irregular": 0.3,
            },
            style="confident, talkative, likes giving opinions",
        ),
    ]
}
