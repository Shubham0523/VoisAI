"""LiveKit agent worker. Run with:
    uv run python -m voisai.agent.worker dev
The browser joins a room with a token from the API; LiveKit dispatches this agent into it.
"""

import json
import logging

from livekit.agents import (
    AgentServer,
    AgentSession,
    APIConnectOptions,
    JobContext,
    JobProcess,
    SessionConnectOptions,
    cli,
    inference,
)
from livekit.plugins import deepgram, openai, silero

from voisai.agent.lifecycle import attach, close_call, open_call
from voisai.config import get_settings

log = logging.getLogger("voisai.worker")
settings = get_settings()


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


def friend_llm() -> openai.LLM:
    kw = {}
    if settings.friend_reasoning_effort:
        kw["reasoning_effort"] = settings.friend_reasoning_effort
    return openai.LLM(
        model=settings.friend_model,
        base_url=settings.friend_base_url,
        api_key=settings.friend_api_key,
        temperature=0.8,
        **kw,
    )


def conn_options() -> SessionConnectOptions:
    return SessionConnectOptions(
        llm_conn_options=APIConnectOptions(timeout=settings.friend_timeout_s, max_retry=2)
    )


server = AgentServer(
    setup_fnc=prewarm,
    ws_url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)


@server.rtc_session(agent_name=settings.agent_name)
async def entrypoint(ctx: JobContext) -> None:
    meta = json.loads(ctx.job.metadata or "{}")
    user_id = meta.get("user_id") or "anonymous"
    l1 = meta.get("native_language") or settings.learner_l1_default

    call = await open_call(user_id, l1, name=meta.get("name"))
    log.info("session %s plan: %s", call.session_id, call.plan.rationale)

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(
            model=settings.stt_model,
            api_key=settings.deepgram_api_key,
            filler_words=True,  # keep "um/uh": fluency signal, and Analyst must see raw speech
            smart_format=False,  # don't let the STT tidy up the learner's grammar
            punctuate=True,
        ),
        llm=friend_llm(),
        conn_options=conn_options(),
        tts=deepgram.TTS(model=settings.tts_voice, api_key=settings.deepgram_api_key),
        turn_handling={
            "turn_detection": inference.TurnDetector(),
            # Learners pause mid-sentence to find words. Cutting them off is the fastest way
            # to make them feel judged, so wait longer than a native-speaker default.
            "endpointing": {"min_delay": 0.8, "max_delay": 4.0},
        },
    )
    attach(call, session)

    async def _shutdown() -> None:
        metrics = await close_call(call)
        log.info("session %s closed: %s", call.session_id, metrics)

    ctx.add_shutdown_callback(_shutdown)

    await session.start(agent=call.agent, room=ctx.room)
    session.generate_reply(instructions=call.opener)


if __name__ == "__main__":
    cli.run_app(server)
