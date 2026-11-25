from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from voisai.config import get_settings
from voisai.db.models import Base

_url = get_settings().database_url
# Transaction poolers (Neon "-pooler", Supabase :6543, PgBouncer) hand each transaction a
# different server connection, so asyncpg's per-connection statement caches must be off.
_POOLED = "-pooler." in _url or ":6543/" in _url
if _POOLED:
    _url += ("&" if "?" in _url else "?") + "prepared_statement_cache_size=0"
engine = create_async_engine(
    _url,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0} if _POOLED else {},
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


async def init_db() -> None:
    """Prototype: create_all on startup. Production would use Alembic migrations."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
