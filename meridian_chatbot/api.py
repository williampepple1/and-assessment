from collections import defaultdict, deque
from time import time
from uuid import uuid4

from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Request

from .agent import ChatbotAgent
from .config import get_settings
from .mcp_client import MeridianMCPClient
from .models import ChatMessage, PendingToolCall
from .observability import log_event


router = APIRouter()
_pending_actions: dict[str, PendingToolCall] = {}
_rate_limits: dict[str, deque[float]] = defaultdict(deque)


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request):
    settings = get_settings()
    conversation_id = request.conversation_id or str(uuid4())
    client_key = _client_key(http_request, conversation_id)

    _enforce_rate_limit(client_key, conversation_id)
    if len(request.history) > settings.max_history_messages:
        log_event(
            "chat_request_rejected",
            conversation_id=conversation_id,
            success=False,
            error_category="conversation_too_long",
            history_length=len(request.history),
        )
        raise HTTPException(
            status_code=400,
            detail=f"Conversation is too long. Keep the last {settings.max_history_messages} messages.",
        )

    agent = ChatbotAgent(settings)
    response = await agent.respond(
        request.message,
        request.history[-settings.max_history_messages :],
        conversation_id=conversation_id,
        pending_action=_pending_actions.get(conversation_id),
    )

    if response.pending_action is not None:
        _pending_actions[conversation_id] = response.pending_action
    else:
        _pending_actions.pop(conversation_id, None)

    return response.model_dump()


@router.get("/tools", response_model=list[ToolInfo])
async def tools():
    client = MeridianMCPClient(get_settings())
    discovered = await client.list_tools()
    return [ToolInfo(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in discovered]


@router.get("/health")
async def health():
    settings = get_settings()
    components = {
        "api": {"status": "ok"},
        "llm": {
            "status": "ok" if settings.openai_api_key else "misconfigured",
            "model": settings.llm_model,
        },
        "mcp": {"status": "unknown"},
    }

    try:
        tools = await MeridianMCPClient(settings).list_tools()
    except Exception as exc:
        components["mcp"] = {"status": "unhealthy", "error": exc.__class__.__name__}
    else:
        components["mcp"] = {"status": "ok", "tool_count": len(tools)}

    status = "ok" if all(component["status"] == "ok" for component in components.values()) else "degraded"
    return {"status": status, "components": components}


def _client_key(request: Request, conversation_id: str) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip_address = forwarded_for.split(",")[0].strip()
    elif request.client:
        ip_address = request.client.host
    else:
        ip_address = "unknown"
    return f"{ip_address}:{conversation_id}"


def _enforce_rate_limit(client_key: str, conversation_id: str) -> None:
    settings = get_settings()
    now = time()
    window_start = now - settings.rate_limit_window_seconds
    timestamps = _rate_limits[client_key]

    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    if len(timestamps) >= settings.rate_limit_messages:
        log_event(
            "chat_request_rejected",
            conversation_id=conversation_id,
            success=False,
            error_category="rate_limited",
            rate_limit_messages=settings.rate_limit_messages,
            rate_limit_window_seconds=settings.rate_limit_window_seconds,
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait and try again.")

    timestamps.append(now)
