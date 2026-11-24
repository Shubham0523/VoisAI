"""`uv run python -m voisai.db` creates the schema."""

import asyncio

from voisai.db.session import init_db

if __name__ == "__main__":
    asyncio.run(init_db())
    print("schema ready")
