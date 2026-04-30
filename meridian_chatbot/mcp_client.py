import asyncio
import json
import logging
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from .config import Settings
from .models import ToolDefinition, ToolResult
from .safety import redact

logger = logging.getLogger(__name__)


class MCPClientError(RuntimeError):
    pass


class MeridianMCPClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @asynccontextmanager
    async def _session(self):
        async with streamablehttp_client(self._settings.mcp_server_url) as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                yield session

    async def list_tools(self) -> list[ToolDefinition]:
        try:
            response = await self._with_retries(lambda: self._list_tools_once())
        except Exception as exc:
            logger.exception("Failed to discover MCP tools")
            raise MCPClientError("Unable to connect to Meridian business tools.") from exc

        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema or {"type": "object", "properties": {}},
            )
            for tool in response.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            response = await self._with_retries(lambda: self._call_tool_once(name, arguments))
        except Exception as exc:
            logger.exception("MCP tool call failed", extra={"tool": name, "arguments": redact(arguments)})
            return ToolResult(
                name=name,
                is_error=True,
                content="The Meridian service is temporarily unavailable. Please try again shortly.",
            )

        content = _serialize_tool_content(response.content)
        is_error = bool(response.isError)
        return ToolResult(
            name=name,
            content=_safe_tool_error(name, content) if is_error else content,
            is_error=is_error,
        )

    async def _list_tools_once(self) -> Any:
        async with self._session() as session:
            return await session.list_tools()

    async def _call_tool_once(self, name: str, arguments: dict[str, Any]) -> Any:
        async with self._session() as session:
            return await session.call_tool(name, arguments)

    async def _with_retries(self, operation: Callable[[], Awaitable[Any]]) -> Any:
        last_error: Exception | None = None
        attempts = self._settings.mcp_max_retries + 1

        for attempt in range(attempts):
            try:
                return await asyncio.wait_for(operation(), timeout=self._settings.mcp_timeout_seconds)
            except Exception as exc:
                last_error = exc
                if attempt == attempts - 1:
                    break
                await asyncio.sleep(self._settings.mcp_retry_backoff_seconds * (attempt + 1))

        if last_error is not None:
            raise last_error
        raise MCPClientError("MCP operation failed.")


def _serialize_tool_content(content: Any) -> str:
    if content is None:
        return ""

    normalized: list[Any] = []
    for item in content if isinstance(content, list) else [content]:
        text = getattr(item, "text", None)
        if text is not None:
            normalized.append(text)
            continue

        data = getattr(item, "data", None)
        if data is not None:
            normalized.append(redact(data))
            continue

        normalized.append(str(item))

    if len(normalized) == 1 and isinstance(normalized[0], str):
        return normalized[0]
    return json.dumps(normalized, default=str)


def _safe_tool_error(name: str, content: str) -> str:
    if name == "create_order":
        return (
            "I could not create the order with the information provided. "
            "Please confirm the customer account and provide each item with SKU, quantity, unit price, and currency."
        )
    if name in {"verify_customer_pin", "get_customer"}:
        return "I could not verify that customer information. Please check the details and try again."
    return "The Meridian service could not complete that request. Please check the details and try again."
