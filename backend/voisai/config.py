"""Central settings, loaded from the repo-root .env (or backend/.env).

Every provider is reached through an OpenAI-compatible endpoint, so swapping
Groq <-> Gemini <-> Cerebras <-> a local Ollama model is an env change, not a code change.
That matters on free tiers: when one provider rate-limits, point a role at another.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        extra="ignore",
    )

    # --- LiveKit (WebRTC transport + agent dispatch). Free "Build" tier on LiveKit Cloud.
    livekit_url: str = "ws://localhost:7880"
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    agent_name: str = "voisai-friend"

    # --- Speech. Deepgram: Nova-3 STT (keeps filler words, word timings) + Aura-2 TTS.
    deepgram_api_key: str = ""
    stt_model: str = "nova-3"
    tts_voice: str = "aura-2-thalia-en"

    # --- LLM roles. Friend must be fast (Groq gpt-oss); Analyst/Planner must be accurate
    # with structured output and can be slower (Gemini Flash, separate free quota).
    friend_base_url: str = "https://api.groq.com/openai/v1"
    friend_api_key: str = ""
    friend_model: str = "openai/gpt-oss-120b"
    friend_reasoning_effort: str | None = "low"  # gpt-oss reasons; "low" keeps replies ~0.6 s
    friend_timeout_s: float = 10.0  # local Ollama shares one GPU with the Analyst: raise it there

    analyst_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    analyst_api_key: str = ""
    analyst_model: str = "gemini-3.5-flash-lite"  # free tier: Flash is 20 req/day, Lite far more
    analyst_reasoning_effort: str | None = None

    # Simulated learners (eval harness) can burn a lot of tokens; give them their own route.
    sim_base_url: str = "https://api.groq.com/openai/v1"
    sim_api_key: str = ""
    sim_model: str = "openai/gpt-oss-20b"
    sim_reasoning_effort: str | None = "low"

    # --- Storage
    database_url: str = "postgresql+asyncpg://voisai:voisai@localhost:5433/voisai"
    embedding_model: str = "BAAI/bge-small-en-v1.5"  # local via fastembed, 384 dims
    embedding_dim: int = 384

    # --- API
    api_cors_origins: list[str] = ["http://localhost:3000"]
    # e.g. https://voisai(-[a-z0-9-]+)?\.vercel\.app to also allow Vercel preview deploys
    api_cors_origin_regex: str | None = None
    # Agent worker pings this (e.g. https://<api>.onrender.com/api/health) so the API never
    # idles into sleep. Unset locally.
    keepalive_url: str | None = None
    keepalive_every_s: float = 600

    # --- Product knobs
    learner_l1_default: str = "Hindi"  # native language assumption; drives L1-specific error priors
    recast_min_confidence: float = 0.8  # only recast errors the Analyst is sure about

    @field_validator("database_url")
    @classmethod
    def _asyncpg_url(cls, v: str) -> str:
        """Accept the plain URL hosts hand out (Neon, Supabase, Render) and adapt it for asyncpg:
        postgres:// -> postgresql+asyncpg://, sslmode=require -> ssl=require, and drop
        libpq-only options asyncpg rejects."""
        from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+asyncpg://" + v[len(prefix) :]
        parts = urlsplit(v)
        q = dict(parse_qsl(parts.query))
        if "sslmode" in q:
            q["ssl"] = q.pop("sslmode")
        q.pop("channel_binding", None)
        return urlunsplit(parts._replace(query=urlencode(q)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
