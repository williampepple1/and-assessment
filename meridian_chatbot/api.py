from pydantic import BaseModel, Field
from fastapi import APIRouter

from .agent import ChatbotAgent
from .config import get_settings
from .mcp_client import MeridianMCPClient
from .models import ChatMessage


router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict


@router.post("/chat")
async def chat(request: ChatRequest):
    agent = ChatbotAgent(get_settings())
    response = await agent.respond(request.message, request.history)
    return response.model_dump()


@router.get("/tools", response_model=list[ToolInfo])
async def tools():
    client = MeridianMCPClient(get_settings())
    discovered = await client.list_tools()
    return [ToolInfo(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in discovered]
