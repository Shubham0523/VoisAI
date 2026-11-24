"""HTTP API: issues LiveKit tokens (with agent dispatch) and serves learner data.
Run with: uv run uvicorn voisai.api.main:app --reload --port 8000"""

import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from pydantic import BaseModel

from voisai.api import progress as progress_api
from voisai.config import get_settings
from voisai.db.session import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        await init_db()
    except Exception as e:  # noqa: BLE001 - API can still issue tokens without the DB
        print(f"[warn] database not ready: {e}")
    yield


app = FastAPI(title="VoisAI", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TokenRequest(BaseModel):
    user_id: str | None = None
    name: str = "friend"
    native_language: str | None = None


class TokenResponse(BaseModel):
    server_url: str
    token: str
    room: str
    user_id: str


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


@app.post("/api/token", response_model=TokenResponse)
async def token(req: TokenRequest) -> TokenResponse:
    if not (settings.livekit_api_key and settings.livekit_api_secret):
        raise HTTPException(500, "LIVEKIT_API_KEY / LIVEKIT_API_SECRET not configured")
    user_id = req.user_id or str(uuid.uuid4())
    room = f"voisai-{user_id[:8]}-{uuid.uuid4().hex[:6]}"
    dispatch_meta = json.dumps(
        {"user_id": user_id, "native_language": req.native_language or settings.learner_l1_default}
    )
    jwt = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(user_id)
        .with_name(req.name)
        .with_grants(api.VideoGrants(room_join=True, room=room))
        .with_room_config(
            api.RoomConfiguration(
                agents=[
                    api.RoomAgentDispatch(agent_name=settings.agent_name, metadata=dispatch_meta)
                ]
            )
        )
        .to_jwt()
    )
    return TokenResponse(server_url=settings.livekit_url, token=jwt, room=room, user_id=user_id)


@app.get("/api/users")
async def users() -> list[dict]:
    return await progress_api.list_users()


@app.get("/api/users/{user_id}/progress")
async def progress(user_id: str) -> dict:
    data = await progress_api.user_progress(user_id)
    if data is None:
        raise HTTPException(404, "unknown user")
    return data


@app.get("/api/eval")
async def eval_results() -> dict:
    return progress_api.eval_results()
