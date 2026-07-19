from __future__ import annotations

import json

import httpx
import pytest

from scripts.ai_admin import KILL_SWITCH_KEY, change_ai_state


@pytest.mark.parametrize(
    ("action", "expected_command", "provider_result", "expected_state"),
    [
        ("status", ["GET", KILL_SWITCH_KEY], "0", "disabled"),
        ("disable", ["SET", KILL_SWITCH_KEY, "0"], "OK", "disabled"),
        ("enable", ["SET", KILL_SWITCH_KEY, "1"], "OK", "enabled"),
    ],
)
def test_ai_admin_uses_the_single_documented_kill_switch(
    action,
    expected_command,
    provider_result,
    expected_state,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        assert json.loads(request.content) == expected_command
        return httpx.Response(200, json={"result": provider_result})

    assert (
        change_ai_state(
            action,
            url="https://redis.example",
            token="token",
            transport=httpx.MockTransport(handler),
        )
        == expected_state
    )
