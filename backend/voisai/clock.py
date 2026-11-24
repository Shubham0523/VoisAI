"""Single source of 'now'. The simulator advances it one day per session so that
follow-ups ("how did Friday's interview go?") become due exactly as they would in real life."""

from datetime import UTC, datetime, timedelta

_offset = timedelta(0)


def now() -> datetime:
    return datetime.now(UTC) + _offset


def advance(days: float) -> None:
    global _offset
    _offset += timedelta(days=days)


def reset() -> None:
    global _offset
    _offset = timedelta(0)
