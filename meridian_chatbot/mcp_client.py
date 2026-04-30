import json
import logging
from contextlib import asynccontextmanager
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
            async with self._session() as session:
                response = await session.list_tools()
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
            async with self._session() as session:
                response = await session.call_tool(name, arguments)
        except Exception as exc:
            logger.exception("MCP tool call failed", extra={"tool": name, "arguments": redact(arguments)})
            return ToolResult(
                name=name,
                is_error=True,
                content="The Meridian service is temporarily unavailable. Please try again shortly.",
            )

        content = _serialize_tool_content(response.content)
        return ToolResult(name=name, content=content, is_error=bool(response.isError))


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
