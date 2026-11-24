"""Fixed skill list the Analyst tags against. A closed list (vs free-text error labels)
is what makes mastery trackable over weeks and comparable across users.

`elicit` is how the Friend can create a natural need for the skill in conversation.
`l1_prone` lists native languages whose speakers commonly struggle with it (transfer errors).
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Skill:
    id: str
    area: str  # grammar | vocabulary | discourse | pragmatics
    name: str
    cefr: str  # level where it is typically expected to be stable
    elicit: str
    l1_prone: tuple[str, ...] = field(default_factory=tuple)


_HI = ("Hindi", "Punjabi", "Marathi", "Bengali", "Tamil", "Telugu")

SKILLS: list[Skill] = [
    # --- Grammar: verbs and tense
    Skill(
        "past_simple",
        "grammar",
        "Past simple",
        "A2",
        "Ask what they did last weekend or yesterday.",
    ),
    Skill(
        "past_irregular",
        "grammar",
        "Irregular past forms",
        "A2",
        "Ask for a story about something that went wrong.",
    ),
    Skill(
        "present_perfect",
        "grammar",
        "Present perfect vs past simple",
        "B1",
        "Ask 'have you ever...' about experiences.",
        _HI,
    ),
    Skill(
        "present_continuous",
        "grammar",
        "Present continuous for now/plans",
        "A2",
        "Ask what they are working on these days.",
        _HI,
    ),
    Skill(
        "stative_continuous",
        "grammar",
        "No continuous with stative verbs ('I am knowing')",
        "B1",
        "Ask what they think or know about a topic.",
        _HI,
    ),
    Skill(
        "future_forms",
        "grammar",
        "Future: will / going to / present continuous",
        "B1",
        "Ask about plans for next month.",
    ),
    Skill(
        "past_continuous",
        "grammar",
        "Past continuous for background",
        "B1",
        "Ask what they were doing when something happened.",
    ),
    Skill(
        "past_perfect",
        "grammar",
        "Past perfect for earlier past",
        "B2",
        "Ask about a time they arrived and something had already happened.",
    ),
    Skill(
        "conditionals_2",
        "grammar",
        "Second conditional (hypotheticals)",
        "B1",
        "Ask what they would do if they won a lot of money.",
    ),
    Skill(
        "conditionals_3",
        "grammar",
        "Third conditional (past regrets)",
        "B2",
        "Ask what they would have done differently in college.",
    ),
    Skill(
        "modals_advice",
        "grammar",
        "Modals: should / could / might",
        "B1",
        "Ask them for advice on a problem you invent.",
    ),
    Skill(
        "modals_deduction",
        "grammar",
        "Modals of deduction (must be, can't be)",
        "B2",
        "Describe a puzzle and ask what they think happened.",
    ),
    Skill(
        "passive",
        "grammar",
        "Passive voice",
        "B1",
        "Ask how something in their city was built or made.",
    ),
    Skill(
        "reported_speech",
        "grammar",
        "Reported speech",
        "B2",
        "Ask what their manager or friend told them recently.",
    ),
    Skill(
        "sv_agreement",
        "grammar",
        "Subject-verb agreement (he goes)",
        "A2",
        "Ask about a family member's daily routine.",
    ),
    Skill(
        "gerund_infinitive",
        "grammar",
        "Gerund vs infinitive (enjoy doing / want to do)",
        "B1",
        "Ask what they enjoy and what they want to try.",
    ),
    # --- Grammar: nouns, articles, structure
    Skill(
        "articles",
        "grammar",
        "Articles a / an / the / zero",
        "B1",
        "Ask them to describe their home or office.",
        _HI,
    ),
    Skill(
        "countable_uncountable",
        "grammar",
        "Countable vs uncountable (advices, informations)",
        "B1",
        "Ask for advice or information on something.",
        _HI,
    ),
    Skill(
        "plurals",
        "grammar",
        "Plural forms",
        "A2",
        "Ask how many friends or siblings they have and about them.",
    ),
    Skill(
        "prepositions_time_place",
        "grammar",
        "Prepositions of time and place (in/on/at)",
        "A2",
        "Ask when and where they usually meet friends.",
        _HI,
    ),
    Skill(
        "prepositions_dependent",
        "grammar",
        "Dependent prepositions (discuss X, depend on)",
        "B2",
        "Ask what their decisions depend on.",
        _HI,
    ),
    Skill(
        "question_formation",
        "grammar",
        "Question formation and word order",
        "A2",
        "Invite them to ask you something.",
        _HI,
    ),
    Skill(
        "indirect_questions",
        "grammar",
        "Indirect questions (can you tell me where it is)",
        "B1",
        "Have them ask you for directions politely.",
        _HI,
    ),
    Skill(
        "comparatives",
        "grammar",
        "Comparatives and superlatives",
        "A2",
        "Ask them to compare two cities or phones.",
    ),
    Skill(
        "relative_clauses",
        "grammar",
        "Relative clauses (who / which / that)",
        "B1",
        "Ask them to describe a person they admire.",
    ),
    Skill(
        "pronoun_gender",
        "grammar",
        "He/she pronoun consistency",
        "A2",
        "Ask about a colleague or friend.",
        ("Hindi", "Tamil", "Telugu"),
    ),
    Skill(
        "word_order_adverbs", "grammar", "Adverb placement", "B1", "Ask how often they do things."
    ),
    # --- Vocabulary
    Skill(
        "collocations",
        "vocabulary",
        "Natural word pairings (make a decision)",
        "B1",
        "Ask about decisions and mistakes they made.",
        _HI,
    ),
    Skill(
        "phrasal_verbs",
        "vocabulary",
        "Common phrasal verbs",
        "B1",
        "Ask about a problem they had to figure out.",
    ),
    Skill(
        "word_choice",
        "vocabulary",
        "Precise word choice",
        "B1",
        "Ask them to describe a feeling in detail.",
    ),
    Skill(
        "lexical_range",
        "vocabulary",
        "Range beyond basic words (good, nice, very)",
        "B2",
        "Ask them to review a film or a restaurant.",
    ),
    Skill(
        "false_friends",
        "vocabulary",
        "Indian-English usages that confuse others (prepone, do the needful)",
        "B2",
        "Ask about scheduling at work.",
        _HI,
    ),
    Skill(
        "idioms",
        "vocabulary",
        "Idioms and set expressions",
        "C1",
        "Tell a story using an idiom and see if they pick it up.",
    ),
    # --- Discourse
    Skill(
        "linking_words",
        "discourse",
        "Linking words (however, although, so)",
        "B1",
        "Ask for pros and cons of something.",
    ),
    Skill(
        "sequencing",
        "discourse",
        "Sequencing a story (first, then, eventually)",
        "B1",
        "Ask for a step-by-step story or recipe.",
    ),
    Skill(
        "elaboration",
        "discourse",
        "Extending answers beyond one sentence",
        "A2",
        "Ask open 'why' and 'how' questions.",
    ),
    Skill(
        "opinion_hedging",
        "discourse",
        "Giving opinions and hedging (I'd say, kind of)",
        "B2",
        "Ask for their take on a mild debate.",
    ),
    # --- Pragmatics
    Skill(
        "politeness",
        "pragmatics",
        "Polite requests and softeners",
        "B1",
        "Role-play asking a favour from a neighbour.",
    ),
    Skill(
        "small_talk",
        "pragmatics",
        "Small talk and follow-up questions",
        "B1",
        "See whether they ask you questions back.",
    ),
    Skill(
        "tag_questions",
        "pragmatics",
        "Tag questions (isn't it?) used correctly",
        "B2",
        "Make statements that invite agreement.",
        _HI,
    ),
]

SKILL_BY_ID: dict[str, Skill] = {s.id: s for s in SKILLS}


def skill_menu() -> str:
    """Compact list for LLM prompts."""
    return "\n".join(f"- {s.id}: {s.name}" for s in SKILLS)
