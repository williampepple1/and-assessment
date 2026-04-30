import logging
from typing import Any

from .config import Settings
from .llm_client import LLMClient, LLMNotConfiguredError, parse_tool_arguments
from .mcp_client import MCPClientError, MeridianMCPClient
from .models import ChatMessage, ChatResponse, ToolDefinition, ToolResult
from .prompts import SYSTEM_PROMPT
from .safety import is_write_tool

logger = logging.getLogger(__name__)


class ChatbotAgent:
    def __init__(
        self,
        settings: Settings,
        mcp_client: MeridianMCPClient | None = None,
        llm_client: LLMClient | None = None,
    ):
        self._settings = settings
        self._mcp_client = mcp_client or MeridianMCPClient(settings)
        self._llm_client = llm_client
        self._tools_cache: list[ToolDefinition] | None = None

    async def respond(self, user_message: str, history: list[ChatMessage]) -> ChatResponse:
        if not user_message.strip():
            return ChatResponse(content="Please enter a message so I can help.")

        try:
            llm_client = self._llm_client or LLMClient(self._settings)
        except LLMNotConfiguredError:
            return ChatResponse(
                content=(
                    "The chatbot is not configured with an LLM API key yet. "
                    "Set OPENAI_API_KEY to enable live responses."
                )
            )

        try:
            tools = await self._get_tools()
        except MCPClientError:
            return ChatResponse(
                content=(
                    "I cannot reach Meridian's order and inventory tools right now. "
                    "Please try again shortly."
                )
            )

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(_trim_history(history))
        messages.append({"role": "user", "content": user_message})

        safe_to_original = {_safe_tool_name(tool.name): tool.name for tool in tools}
        tool_results: list[ToolResult] = []

        for _ in range(self._settings.max_tool_rounds):
            completion = await llm_client.create_response(messages, _safe_tool_definitions(tools))
            assistant_message = completion.choices[0].message
            messages.append(assistant_message.model_dump(exclude_none=True))

            if not assistant_message.tool_calls:
                return ChatResponse(content=assistant_message.content or "", tool_results=tool_results)

            for tool_call in assistant_message.tool_calls:
                safe_name = tool_call.function.name
                original_name = safe_to_original.get(safe_name, safe_name)

                if is_write_tool(original_name) and not _looks_confirmed(user_message):
                    return ChatResponse(
                        content=(
                            "Before I make that change, please confirm the details in one message. "
                            "I will only submit an order or update after you explicitly confirm."
                        ),
                        tool_results=tool_results,
                    )

                try:
                    arguments = parse_tool_arguments(tool_call.function.arguments)
                except ValueError:
                    result = ToolResult(
                        name=original_name,
                        is_error=True,
                        content="The assistant produced invalid tool arguments.",
                    )
                else:
                    result = await self._mcp_client.call_tool(original_name, arguments)

                tool_results.append(result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content,
                    }
                )

        logger.warning("Maximum tool rounds reached")
        return ChatResponse(
            content="I need a little more information to complete that request. Could you rephrase it?",
            tool_results=tool_results,
        )

    async def _get_tools(self) -> list[ToolDefinition]:
        if self._tools_cache is None:
            self._tools_cache = await self._mcp_client.list_tools()
        return self._tools_cache


def _safe_tool_definitions(tools: list[ToolDefinition]) -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name=_safe_tool_name(tool.name),
            description=tool.description,
            input_schema=tool.input_schema,
        )
        for tool in tools
    ]


def _safe_tool_name(name: str) -> str:
    return name.replace("-", "_").replace(" ", "_")


def _trim_history(history: list[ChatMessage], max_messages: int = 12) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in history[-max_messages:]
        if message.role in {"user", "assistant"} and message.content
    ]


def _looks_confirmed(message: str) -> bool:
    normalized = message.lower()
    confirmations = (
        "i confirm",
        "confirm",
        "yes place",
        "yes submit",
        "go ahead",
        "place the order",
        "submit the order",
    )
    return any(phrase in normalized for phrase in confirmations)
