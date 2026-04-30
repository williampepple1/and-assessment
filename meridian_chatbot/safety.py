from collections.abc import Mapping
from typing import Any


SENSITIVE_KEYS = {
    "password",
    "passcode",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "api_key",
    "authorization",
    "otp",
    "one_time_code",
}


def redact(value: Any) -> Any:
    """Redact sensitive values before logging or returning diagnostic data."""

    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if str(key).lower() in SENSITIVE_KEYS else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def is_write_tool(tool_name: str) -> bool:
    normalized = tool_name.lower()
    write_markers = ("create", "place", "submit", "update", "delete", "cancel", "purchase")
    return any(marker in normalized for marker in write_markers)
