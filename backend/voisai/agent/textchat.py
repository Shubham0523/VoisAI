"""Text-mode calls through the real Friend + Tutor pipeline (no audio).

Used by the simulated-learner evals and tests, and handy for prompt work:
    uv run python -m voisai.agent.textchat --user me
"""

import argparse
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from livekit.agents import AgentSession

from voisai.agent.lifecycle import Call, attach, close_call, open_call
from voisai.agent.worker import conn_options, friend_llm


@dataclass
class Transcript:
    call: Call
    turns: list[tuple[str, str]] = field(default_factory=list)  # (role, text)
    metrics: dict = field(default_factory=dict)
    hints: list[str | None] = field(default_factory=list)


# Given the transcript so far, return the next user utterance (None ends the call).
UserFn = Callable[[list[tuple[str, str]]], Awaitable[str | None]]


async def run_text_call(
    user_id: str,
    l1: str,
    next_user: UserFn,
    max_turns: int = 10,
    summarize: bool = True,
    name: str | None = None,
) -> Transcript:
    call = await open_call(user_id, l1, name=name)
    tr = Transcript(call)
    async with AgentSession(llm=friend_llm(), conn_options=conn_options()) as session:
        attach(call, session)
        session.on(
            "conversation_item_added",
            lambda ev: (
                getattr(ev.item, "role", None) in ("user", "assistant")
                and ev.item.text_content
                and tr.turns.append((ev.item.role, ev.item.text_content))
            ),
        )
        await session.start(call.agent)
        await session.generate_reply(instructions=call.opener)
        for _ in range(max_turns):
            text = await next_user(tr.turns)
            if not text:
                break
            await session.run(user_input=text)
            tr.hints.append(call.agent.last_hint)
    tr.metrics = await close_call(call, summarize=summarize)
    return tr


async def _interactive(user_id: str, l1: str) -> None:
    loop = asyncio.get_running_loop()
    printed = 0

    async def next_user(turns):
        nonlocal printed
        for role, text in turns[printed:]:
            if role == "assistant":
                print(f"\nMaya: {text}")
        printed = len(turns)
        line = await loop.run_in_executor(None, input, "\nYou: ")
        printed += 1
        return None if line.strip() in {"", "/quit"} else line

    tr = await run_text_call(user_id, l1, next_user, max_turns=100)
    print("\n--- session metrics ---")
    for k, v in tr.metrics.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--user", default="cli-user")
    p.add_argument("--l1", default="Hindi")
    a = p.parse_args()
    asyncio.run(_interactive(a.user, a.l1))
