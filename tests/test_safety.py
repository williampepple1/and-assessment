from meridian_chatbot.safety import is_write_tool, redact


def test_redact_nested_sensitive_values():
    payload = {
        "email": "customer@example.com",
        "token": "secret-token",
        "profile": {"password": "hidden", "name": "Ada"},
    }

    assert redact(payload) == {
        "email": "customer@example.com",
        "token": "[REDACTED]",
        "profile": {"password": "[REDACTED]", "name": "Ada"},
    }


def test_write_tool_detection():
    assert is_write_tool("create_order")
    assert is_write_tool("submitOrder")
    assert not is_write_tool("lookup_order_history")
