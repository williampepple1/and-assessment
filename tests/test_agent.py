from types import SimpleNamespace

import pytest

from meridian_chatbot.agent import ChatbotAgent
from meridian_chatbot.config import Settings
from meridian_chatbot.models import ToolDefinition, ToolResult


class FakeMCPClient:
    def __init__(self):
        self.called = False

    async def list_tools(self):
        return [
            ToolDefinition(
                name="create_order",
                description="Create a customer order.",
                input_schema={"type": "object", "properties": {"sku": {"type": "string"}}},
            )
        ]

    async def call_tool(self, name, arguments):
        self.called = True
        return ToolResult(name=name, content="created")


class FakeLLMClient:
    async def create_response(self, messages, tools):
        message = FakeAssistantMessage(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    id="call_1",
                    function=SimpleNamespace(name="create_order", arguments='{"sku":"MON-1"}'),
                )
            ],
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeAssistantMessage:
    def __init__(self, content, tool_calls):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        return {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ],
        }


@pytest.mark.asyncio
async def test_agent_requires_confirmation_before_write_tool():
    mcp_client = FakeMCPClient()
    agent = ChatbotAgent(
        Settings(OPENAI_API_KEY="test-key"),
        mcp_client=mcp_client,
        llm_client=FakeLLMClient(),
    )

    response = await agent.respond("Order one monitor for me", [])

    assert "confirm" in response.content.lower()
    assert mcp_client.called is False
