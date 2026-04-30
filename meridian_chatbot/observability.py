import json
import logging
from time import perf_counter
from typing import Any

from .safety import redact

logger = logging.getLogger("meridian_chatbot.telemetry")


class Timer:
    def __init__(self) -> None:
        self._start = perf_counter()

    def elapsed_ms(self) -> float:
        return round((perf_counter() - self._start) * 1000, 2)


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **redact(fields)}
    logger.info(json.dumps(payload, default=str, sort_keys=True))


def usage_to_dict(usage: Any) -> dict[str, int | None]:
    if usage is None:
        return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
