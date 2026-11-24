"""LLM clients per role. All OpenAI-compatible, so any free provider (or local Ollama)
plugs in via env."""

import json
import re
from functools import lru_cache
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from voisai.config import get_settings

Role = Literal["friend", "analyst", "sim"]


def _cfg(role: Role) -> tuple[str, str, str, str | None]:
    s = get_settings()
    return {
        "friend": (s.friend_base_url, s.friend_api_key, s.friend_model, s.friend_reasoning_effort),
        "analyst": (
            s.analyst_base_url,
            s.analyst_api_key,
            s.analyst_model,
            s.analyst_reasoning_effort,
        ),
        "sim": (s.sim_base_url, s.sim_api_key, s.sim_model, s.sim_reasoning_effort),
    }[role]


@lru_cache
def client(role: Role) -> AsyncOpenAI:
    base_url, api_key, _, _ = _cfg(role)
    return AsyncOpenAI(base_url=base_url, api_key=api_key or "missing", max_retries=5, timeout=120)


def model(role: Role) -> str:
    return _cfg(role)[2]


def extra_args(role: Role) -> dict[str, Any]:
    effort = _cfg(role)[3]
    return {"reasoning_effort": effort} if effort else {}


async def chat(role: Role, messages: list[dict], temperature: float = 0.7, **kw: Any) -> str:
    resp = await client(role).chat.completions.create(
        model=model(role),
        messages=messages,
        temperature=temperature,
        **extra_args(role),
        **kw,
    )
    return _strip_think(resp.choices[0].message.content or "")


def _strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def parse_json[T: BaseModel](text: str, schema: type[T]) -> T:
    """Tolerates code fences and leading prose, which free/local models sometimes add."""
    text = _strip_think(text)
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        pass
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in model output: {text[:200]!r}")
    return schema.model_validate(json.loads(m.group(0)))


async def structured[T: BaseModel](
    role: Role, system: str, user: str, schema: type[T], example: str | None = None
) -> T:
    """One structured-output call: JSON mode + Pydantic validation (rather than a
    provider-specific `response_format=schema`, since free providers differ in how much
    JSON Schema they accept). A compact `example` instead of the full schema keeps the prompt
    small, which matters on free tiers and small local context windows. One retry with the validation error on failure."""
    messages = [
        {
            "role": "system",
            "content": f"{system}\n\nRespond ONLY with a JSON object "
            + (
                f"in exactly this shape:\n{example}"
                if example
                else f"matching this JSON schema:\n{json.dumps(schema.model_json_schema())}"
            ),
        },
        {"role": "user", "content": user},
    ]
    out = await chat(role, messages, temperature=0.1, response_format={"type": "json_object"})
    try:
        return parse_json(out, schema)
    except (ValueError, ValidationError) as e:
        messages += [
            {"role": "assistant", "content": out},
            {
                "role": "user",
                "content": f"That was invalid ({str(e)[:300]}). Return corrected JSON only.",
            },
        ]
        out = await chat(role, messages, temperature=0.0, response_format={"type": "json_object"})
        return parse_json(out, schema)
