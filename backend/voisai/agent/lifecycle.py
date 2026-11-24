"""Session setup/teardown shared by the voice worker and the text harness, so simulated
learners and tests go through exactly what a real call goes through."""

import logging
import uuid
from dataclasses import dataclass

from livekit.agents import AgentSession, ConversationItemAddedEvent

from voisai.agent.friend import FriendAgent
from voisai.agent.persona import OPENER_FIRST_TIME
from voisai.agent.recorder import Recorder
from voisai.memory import store
from voisai.tutor.planner import SessionPlan, plan_session
from voisai.tutor.session_end import finalize_session

log = logging.getLogger("voisai.lifecycle")


@dataclass
class Call:
    user_id: str
    session_id: str
    plan: SessionPlan
    recorder: Recorder
    agent: FriendAgent

    @property
    def opener(self) -> str:
        return self.plan.opener or OPENER_FIRST_TIME


async def open_call(user_id: str, l1: str, name: str | None = None, analyze: bool = True) -> Call:
    session_id = str(uuid.uuid4())
    recorder = Recorder(user_id, session_id)
    await recorder.start(None, l1=l1, name=name)  # creates the user row before planning

    try:
        plan = await plan_session(user_id)
        facts = await store.profile(user_id)
        await recorder.update_plan(plan.model_dump())
    except Exception:
        log.exception("planning failed; using a cold-start plan")
        plan, facts = SessionPlan(rationale="planner unavailable"), []

    memory = "\n".join(f"- {f}" for f in facts)
    agent = FriendAgent(recorder, plan, l1, memory_context=memory, analyze=analyze)
    return Call(user_id, session_id, plan, recorder, agent)


def attach(call: Call, session: AgentSession) -> None:
    @session.on("conversation_item_added")
    def _on_item(ev: ConversationItemAddedEvent) -> None:
        item = ev.item
        if getattr(item, "role", None) == "assistant" and item.text_content:
            call.agent.on_assistant_message(item.text_content)


async def close_call(call: Call, summarize: bool = True) -> dict:
    await call.agent.drain()
    if not call.recorder.enabled:
        return {}
    try:
        return await finalize_session(call.session_id, summarize=summarize)
    except Exception:
        log.exception("finalize failed")
        return {}
