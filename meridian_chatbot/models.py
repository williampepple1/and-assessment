from typing import Any
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    name: str
    content: str
    is_error: bool = False


class PendingToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str


class ChatResponse(BaseModel):
    conversation_id: str | None = None
    content: str
    tool_results: list[ToolResult] = Field(default_factory=list)
    pending_action: PendingToolCall | None = None
