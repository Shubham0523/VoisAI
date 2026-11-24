"""Long-term memory: pgvector similarity + due follow-ups. Embeddings run locally
(fastembed, small ONNX model) so memory costs nothing and never leaves the machine."""

import asyncio
from datetime import datetime, timedelta
from functools import lru_cache

from sqlalchemy import select

from voisai import clock
from voisai.config import get_settings
from voisai.db.models import Memory
from voisai.db.session import db


@lru_cache
def _embedder():
    from fastembed import TextEmbedding  # lazy: model download on first use

    return TextEmbedding(get_settings().embedding_model)


def embed_sync(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _embedder().embed(texts)]


async def embed(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(embed_sync, texts)


async def remember(
    user_id: str,
    session_id: str | None,
    items: list[tuple[str, str, int | None]],  # (text, kind, due_in_days)
    dedupe_threshold: float = 0.08,
) -> int:
    """Store memories, skipping near-duplicates of what we already know."""
    if not items:
        return 0
    vecs = await embed([t for t, _, _ in items])
    now = clock.now()
    added = 0
    async with db() as s:
        for (text, kind, due), vec in zip(items, vecs, strict=True):
            dist = (
                await s.execute(
                    select(Memory.embedding.cosine_distance(vec))
                    .where(Memory.user_id == user_id)
                    .order_by(Memory.embedding.cosine_distance(vec))
                    .limit(1)
                )
            ).scalar()
            if dist is not None and dist < dedupe_threshold:
                continue
            kind = kind if kind in {"fact", "event", "preference", "followup"} else "fact"
            s.add(
                Memory(
                    user_id=user_id,
                    session_id=session_id,
                    kind=kind,
                    text=text,
                    embedding=vec,
                    due_at=now + timedelta(days=due)
                    if kind == "followup" and due is not None
                    else None,
                )
            )
            added += 1
    return added


async def recall(user_id: str, query: str, k: int = 5) -> list[str]:
    [vec] = await embed([query])
    async with db() as s:
        rows = await s.execute(
            select(Memory.text)
            .where(Memory.user_id == user_id)
            .order_by(Memory.embedding.cosine_distance(vec))
            .limit(k)
        )
        return list(rows.scalars())


async def profile(user_id: str, limit: int = 12) -> list[str]:
    """Most recent stable facts, for the Friend's system prompt at session start."""
    async with db() as s:
        rows = await s.execute(
            select(Memory.text)
            .where(Memory.user_id == user_id, Memory.kind.in_(["fact", "preference", "event"]))
            .order_by(Memory.created_at.desc())
            .limit(limit)
        )
        return list(rows.scalars())


async def due_followups(user_id: str, now: datetime | None = None) -> list[Memory]:
    now = now or clock.now()
    async with db() as s:
        rows = await s.execute(
            select(Memory)
            .where(
                Memory.user_id == user_id,
                Memory.kind == "followup",
                Memory.resolved.is_(False),
                Memory.due_at <= now,
            )
            .order_by(Memory.due_at)
        )
        return list(rows.scalars())


async def resolve(memory_ids: list[str]) -> None:
    if not memory_ids:
        return
    async with db() as s:
        for m in (await s.execute(select(Memory).where(Memory.id.in_(memory_ids)))).scalars():
            m.resolved = True
