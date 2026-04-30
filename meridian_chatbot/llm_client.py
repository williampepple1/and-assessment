import json
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .models import ChatMessage, ToolDefinition


class LLMNotConfiguredError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise LLMNotConfiguredError("OPENAI_API_KEY is required to use the chatbot.")

        self._settings = settings
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.request_timeout_seconds,
        )

    async def create_response(
        self,
        messages: list[dict[str, Any] | ChatMessage],
        tools: list[ToolDefinition],
    ) -> Any:
        normalized_messages = [
            message.model_dump() if isinstance(message, ChatMessage) else message
            for message in messages
        ]

        return await self._client.chat.completions.create(
            model=self._settings.llm_model,
            messages=normalized_messages,
            tools=[_to_openai_tool(tool) for tool in tools],
            tool_choice="auto" if tools else None,
            temperature=0.2,
        )


def _to_openai_tool(tool: ToolDefinition) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": _safe_tool_name(tool.name),
            "description": tool.description or f"Call Meridian tool {tool.name}",
            "parameters": tool.input_schema or {"type": "object", "properties": {}},
        },
    }


def parse_tool_arguments(raw_arguments: str | None) -> dict[str, Any]:
    if not raw_arguments:
        return {}
    parsed = json.loads(raw_arguments)
    if not isinstance(parsed, dict):
        raise ValueError("Tool arguments must be a JSON object.")
    return parsed


def _safe_tool_name(name: str) -> str:
    return name.replace("-", "_").replace(" ", "_")
