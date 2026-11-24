"""Data model. Two halves: what happened (sessions, turns, observations) and what we
believe about the learner (skill mastery, vocabulary, memories). Beliefs are always
re-derivable from observations, which keeps the learner model auditable."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from voisai.config import get_settings

EMBED_DIM = get_settings().embedding_dim


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, default="friend")
    native_language: Mapped[str] = mapped_column(String, default="Hindi")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    persona: Mapped[dict | None] = mapped_column(JSON)  # sim learners: planted error profile
    estimated_cefr: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConversationSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan: Mapped[dict | None] = mapped_column(JSON)  # Planner output: target skills, words, hints
    summary: Mapped[str | None] = mapped_column(Text)
    recap: Mapped[dict | None] = mapped_column(JSON)  # optional "by the way" card
    metrics: Mapped[dict | None] = mapped_column(JSON)  # per-session rollup for the dashboard
    is_benchmark: Mapped[bool] = mapped_column(Boolean, default=False)  # fixed story task

    turns: Mapped[list["Turn"]] = relationship(back_populates="session", order_by="Turn.idx")


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    idx: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String)  # "user" | "assistant"
    text: Mapped[str] = mapped_column(Text)
    words: Mapped[list | None] = mapped_column(JSON)  # [{w, start, end, conf}] from STT
    fluency: Mapped[dict | None] = mapped_column(JSON)  # wpm, pauses, fillers ...
    hint: Mapped[str | None] = mapped_column(Text)  # hidden Tutor instruction used for this reply
    benchmark: Mapped[bool] = mapped_column(
        Boolean, default=False
    )  # answer to the fixed story task
    analysis_ms: Mapped[int | None] = mapped_column(Integer)  # Analyst latency, for ops
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session: Mapped[ConversationSession] = relationship(back_populates="turns")


class Observation(Base):
    """One piece of evidence about one skill: the user produced it right or wrong in a
    context that required it. Correct uses matter as much as errors, otherwise mastery
    can only ever go down."""

    __tablename__ = "observations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey("turns.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[str] = mapped_column(String, index=True)
    correct: Mapped[bool] = mapped_column(Boolean)
    span: Mapped[str | None] = mapped_column(Text)  # what they said
    correction: Mapped[str | None] = mapped_column(Text)  # what a fluent speaker would say
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillMastery(Base):
    """Beta(alpha, beta) belief over P(correct | obligatory context) per skill."""

    __tablename__ = "skill_mastery"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    skill_id: Mapped[str] = mapped_column(String, primary_key=True)
    alpha: Mapped[float] = mapped_column(Float, default=1.0)
    beta: Mapped[float] = mapped_column(Float, default=1.0)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VocabItem(Base):
    """Lifecycle of a word the Friend seeded: introduced -> recognised -> used unprompted."""

    __tablename__ = "vocab"
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    word: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, default="introduced")
    introduced_session_id: Mapped[str | None] = mapped_column(String)
    first_used_session_id: Mapped[str | None] = mapped_column(String)
    times_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Memory(Base):
    """Things a friend would remember. `kind=followup` + `due_at` powers
    "how did Friday's interview go?", which is also free past-tense practice."""

    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)  # "fact" | "event" | "followup" | "preference"
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
