import logging
from typing import Any

from .config import Settings
from .llm_client import LLMClient, LLMNotConfiguredError, parse_tool_arguments
from .mcp_client import MCPClientError, MeridianMCPClient
from .models import ChatMessage, ChatResponse, PendingToolCall, ToolDefinition, ToolResult
from .observability import Timer, log_event, usage_to_dict
from .prompts import SYSTEM_PROMPT
from .safety import is_write_tool, redact

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

    async def respond(
        self,
        user_message: str,
        history: list[ChatMessage],
        conversation_id: str,
        pending_action: PendingToolCall | None = None,
    ) -> ChatResponse:
        request_timer = Timer()
        total_llm_latency_ms = 0.0
        total_tool_latency_ms = 0.0
        token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        log_event("chat_request_started", conversation_id=conversation_id)

        if not user_message.strip():
            log_event(
                "chat_request_completed",
                conversation_id=conversation_id,
                success=False,
                error_category="validation",
                latency_ms=request_timer.elapsed_ms(),
            )
            return ChatResponse(
                conversation_id=conversation_id,
                content="Please enter a message so I can help.",
            )

        if pending_action is not None:
            if _is_rejection(user_message):
                log_event(
                    "pending_action_cancelled",
                    conversation_id=conversation_id,
                    tool_name=pending_action.name,
                )
                return ChatResponse(
                    conversation_id=conversation_id,
                    content="No problem. I cancelled that pending action.",
                )

            if _is_confirmation(user_message):
                tool_timer = Timer()
                result = await self._mcp_client.call_tool(pending_action.name, pending_action.arguments)
                total_tool_latency_ms += tool_timer.elapsed_ms()
                log_event(
                    "tool_call_completed",
                    conversation_id=conversation_id,
                    tool_name=pending_action.name,
                    tool_latency_ms=total_tool_latency_ms,
                    success=not result.is_error,
                    error_category="mcp" if result.is_error else None,
                )
                log_event(
                    "chat_request_completed",
                    conversation_id=conversation_id,
                    tool_name=pending_action.name,
                    tool_latency_ms=total_tool_latency_ms,
                    llm_latency_ms=total_llm_latency_ms,
                    token_usage=token_usage,
                    success=not result.is_error,
                    error_category="mcp" if result.is_error else None,
                    latency_ms=request_timer.elapsed_ms(),
                )
                prefix = "Confirmed. " if not result.is_error else ""
                return ChatResponse(
                    conversation_id=conversation_id,
                    content=f"{prefix}{result.content}",
                    tool_results=[result],
                )

            return ChatResponse(
                conversation_id=conversation_id,
                content=(
                    "I still have this pending action waiting for your confirmation:\n\n"
                    f"{pending_action.summary}\n\n"
                    "Please reply with 'confirm' to continue or 'cancel' to stop."
                ),
                pending_action=pending_action,
            )

        try:
            llm_client = self._llm_client or LLMClient(self._settings)
        except LLMNotConfiguredError:
            log_event(
                "chat_request_completed",
                conversation_id=conversation_id,
                success=False,
                error_category="llm_configuration",
                latency_ms=request_timer.elapsed_ms(),
            )
            return ChatResponse(
                conversation_id=conversation_id,
                content=(
                    "The chatbot is not configured with an LLM API key yet. "
                    "Set OPENAI_API_KEY to enable live responses."
                )
            )

        try:
            tools = await self._get_tools()
        except MCPClientError:
            log_event(
                "chat_request_completed",
                conversation_id=conversation_id,
                success=False,
                error_category="mcp_discovery",
                latency_ms=request_timer.elapsed_ms(),
            )
            return ChatResponse(
                conversation_id=conversation_id,
                content=(
                    "I cannot reach Meridian's order and inventory tools right now. "
                    "Please try again shortly."
                )
            )

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(_trim_history(history, self._settings.max_history_messages))
        messages.append({"role": "user", "content": user_message})

        safe_to_original = {_safe_tool_name(tool.name): tool.name for tool in tools}
        tool_results: list[ToolResult] = []

        for _ in range(self._settings.max_tool_rounds):
            llm_timer = Timer()
            try:
                completion = await llm_client.create_response(messages, _safe_tool_definitions(tools))
            except Exception:
                logger.exception("LLM call failed")
                log_event(
                    "chat_request_completed",
                    conversation_id=conversation_id,
                    llm_latency_ms=llm_timer.elapsed_ms(),
                    tool_latency_ms=total_tool_latency_ms,
                    token_usage=token_usage,
                    success=False,
                    error_category="llm",
                    latency_ms=request_timer.elapsed_ms(),
                )
                return ChatResponse(
                    conversation_id=conversation_id,
                    content="I am having trouble reaching the AI service right now. Please try again shortly.",
                    tool_results=tool_results,
                )
            llm_latency_ms = llm_timer.elapsed_ms()
            total_llm_latency_ms += llm_latency_ms
            token_usage = _add_usage(token_usage, usage_to_dict(getattr(completion, "usage", None)))
            log_event(
                "llm_call_completed",
                conversation_id=conversation_id,
                llm_latency_ms=llm_latency_ms,
                token_usage=usage_to_dict(getattr(completion, "usage", None)),
                success=True,
            )
            assistant_message = completion.choices[0].message
            messages.append(assistant_message.model_dump(exclude_none=True))

            if not assistant_message.tool_calls:
                log_event(
                    "chat_request_completed",
                    conversation_id=conversation_id,
                    llm_latency_ms=total_llm_latency_ms,
                    tool_latency_ms=total_tool_latency_ms,
                    token_usage=token_usage,
                    success=True,
                    latency_ms=request_timer.elapsed_ms(),
                )
                return ChatResponse(
                    conversation_id=conversation_id,
                    content=assistant_message.content or "",
                    tool_results=tool_results,
                )

            for tool_call in assistant_message.tool_calls:
                safe_name = tool_call.function.name
                original_name = safe_to_original.get(safe_name, safe_name)
                tool_definition = _find_tool(tools, original_name)

                try:
                    arguments = parse_tool_arguments(tool_call.function.arguments)
                except ValueError:
                    result = ToolResult(
                        name=original_name,
                        is_error=True,
                        content="The assistant produced invalid tool arguments.",
                    )
                    log_event(
                        "tool_call_completed",
                        conversation_id=conversation_id,
                        tool_name=original_name,
                        success=False,
                        error_category="tool_arguments",
                    )
                else:
                    argument_issue = _validate_tool_arguments(tool_definition, arguments)
                    if argument_issue is not None:
                        log_event(
                            "tool_call_completed",
                            conversation_id=conversation_id,
                            tool_name=original_name,
                            success=False,
                            error_category="tool_arguments",
                        )
                        return ChatResponse(
                            conversation_id=conversation_id,
                            content=argument_issue,
                            tool_results=tool_results,
                        )

                    if is_write_tool(original_name):
                        pending = PendingToolCall(
                            name=original_name,
                            arguments=arguments,
                            summary=_pending_summary(original_name, arguments),
                        )
                        log_event(
                            "pending_action_created",
                            conversation_id=conversation_id,
                            tool_name=original_name,
                            success=True,
                        )
                        return ChatResponse(
                            conversation_id=conversation_id,
                            content=(
                                "Before I make that change, please confirm this exact action:\n\n"
                                f"{pending.summary}\n\n"
                                "Reply with 'confirm' to continue or 'cancel' to stop."
                            ),
                            tool_results=tool_results,
                            pending_action=pending,
                        )

                    tool_timer = Timer()
                    result = await self._mcp_client.call_tool(original_name, arguments)
                    tool_latency_ms = tool_timer.elapsed_ms()
                    total_tool_latency_ms += tool_latency_ms
                    log_event(
                        "tool_call_completed",
                        conversation_id=conversation_id,
                        tool_name=original_name,
                        tool_latency_ms=tool_latency_ms,
                        success=not result.is_error,
                        error_category="mcp" if result.is_error else None,
                    )

                tool_results.append(result)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result.content,
                    }
                )

        logger.warning("Maximum tool rounds reached")
        log_event(
            "chat_request_completed",
            conversation_id=conversation_id,
            llm_latency_ms=total_llm_latency_ms,
            tool_latency_ms=total_tool_latency_ms,
            token_usage=token_usage,
            success=False,
            error_category="max_tool_rounds",
            latency_ms=request_timer.elapsed_ms(),
        )
        return ChatResponse(
            conversation_id=conversation_id,
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


def _find_tool(tools: list[ToolDefinition], name: str) -> ToolDefinition | None:
    return next((tool for tool in tools if tool.name == name), None)


def _validate_tool_arguments(tool: ToolDefinition | None, arguments: dict[str, Any]) -> str | None:
    if tool is None:
        return None

    required_fields = tool.input_schema.get("required", [])
    missing = [field for field in required_fields if field not in arguments or arguments[field] in (None, "", [])]
    if missing:
        return _missing_fields_message(tool.name, missing)

    if tool.name == "create_order":
        customer_id = str(arguments.get("customer_id", ""))
        items = arguments.get("items")
        if "@" in customer_id:
            return (
                "Before I can create the order, I need to verify the customer and use their customer ID, "
                "not their email address. Please authenticate the customer first."
            )
        if not isinstance(items, list) or not items:
            return "Before I can create the order, please provide at least one item with SKU, quantity, unit price, and currency."

        required_item_fields = {"sku", "quantity", "unit_price", "currency"}
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                return f"Item {index} is not valid. Please provide SKU, quantity, unit price, and currency."
            missing_item_fields = sorted(field for field in required_item_fields if field not in item or item[field] in (None, ""))
            if missing_item_fields:
                return f"Item {index} is missing: {', '.join(missing_item_fields)}."

    return None


def _missing_fields_message(tool_name: str, missing: list[str]) -> str:
    if tool_name == "create_order":
        return (
            "Before I can create the order, I need the customer ID and an items list. "
            "Each item should include SKU, quantity, unit price, and currency."
        )
    return f"I need the following information before I can continue: {', '.join(missing)}."


def _trim_history(history: list[ChatMessage], max_messages: int = 12) -> list[dict[str, str]]:
    return [
        {"role": message.role, "content": message.content}
        for message in history[-max_messages:]
        if message.role in {"user", "assistant"} and message.content
    ]


def _is_confirmation(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"confirm", "i confirm", "yes", "yes confirm", "go ahead", "proceed"}


def _is_rejection(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"cancel", "stop", "no", "do not proceed", "never mind", "nevermind"}


def _pending_summary(tool_name: str, arguments: dict[str, Any]) -> str:
    lines = [f"Tool: {tool_name}", "Arguments:"]
    safe_arguments = redact(arguments)
    for key in sorted(safe_arguments):
        lines.append(f"- {key}: {safe_arguments[key]}")
    return "\n".join(lines)


def _add_usage(
    total: dict[str, int | None],
    current: dict[str, int | None],
) -> dict[str, int | None]:
    return {
        key: (total.get(key) or 0) + (current.get(key) or 0)
        for key in {"prompt_tokens", "completion_tokens", "total_tokens"}
    }
