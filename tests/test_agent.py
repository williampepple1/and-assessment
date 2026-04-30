from types import SimpleNamespace

import pytest

from meridian_chatbot.agent import ChatbotAgent
from meridian_chatbot.config import Settings
from meridian_chatbot.models import PendingToolCall, ToolDefinition, ToolResult


class FakeMCPClient:
    def __init__(self):
        self.called = False

    async def list_tools(self):
        return [
            ToolDefinition(
                name="create_order",
                description="Create a customer order.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "customer_id": {"type": "string"},
                        "items": {"type": "array"},
                    },
                    "required": ["customer_id", "items"],
                },
            )
        ]

    async def call_tool(self, name, arguments):
        self.called = True
        return ToolResult(name=name, content="created")


class FakeLLMClient:
    def __init__(self, arguments='{"customer_id":"customer-123","items":[{"sku":"MON-1","quantity":1,"unit_price":"199.99","currency":"USD"}]}'):
        self.arguments = arguments

    async def create_response(self, messages, tools):
        message = FakeAssistantMessage(
            content=None,
            tool_calls=[
                SimpleNamespace(
                    id="call_1",
                    function=SimpleNamespace(name="create_order", arguments=self.arguments),
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

    response = await agent.respond("Order one monitor for me", [], conversation_id="test-conversation")

    assert "confirm" in response.content.lower()
    assert mcp_client.called is False
    assert response.pending_action is not None


@pytest.mark.asyncio
async def test_agent_asks_for_missing_create_order_items():
    mcp_client = FakeMCPClient()
    agent = ChatbotAgent(
        Settings(OPENAI_API_KEY="test-key"),
        mcp_client=mcp_client,
        llm_client=FakeLLMClient(arguments='{"customer_id":"williamsthomas@example.net"}'),
    )

    response = await agent.respond("Order one monitor for me", [], conversation_id="test-conversation")

    assert "items list" in response.content.lower()
    assert "unit price" in response.content.lower()
    assert mcp_client.called is False
    assert response.pending_action is None


@pytest.mark.asyncio
async def test_agent_executes_stored_pending_action_only_after_confirmation():
    mcp_client = FakeMCPClient()
    agent = ChatbotAgent(
        Settings(OPENAI_API_KEY="test-key"),
        mcp_client=mcp_client,
        llm_client=FakeLLMClient(),
    )
    pending_action = PendingToolCall(
        name="create_order",
        arguments={
            "customer_id": "customer-123",
            "items": [{"sku": "MON-1", "quantity": 1, "unit_price": "199.99", "currency": "USD"}],
        },
        summary="Tool: create_order\nArguments:\n- customer_id: customer-123",
    )

    response = await agent.respond(
        "confirm",
        [],
        conversation_id="test-conversation",
        pending_action=pending_action,
    )

    assert response.content.startswith("Confirmed.")
    assert mcp_client.called is True
    assert response.pending_action is None
