from __future__ import annotations

import json

import httpx
import pytest
from fastapi import Request

from dau import app as app_module
from dau.app import _finish_reveal_permit, _issue_reveal_permit, _read_reveal_permit
from dau.guards import (
    _WINDOW_SCRIPT,
    GuardIdentity,
    InMemoryGuard,
    LimitPolicy,
    UpstashGuard,
    request_identity,
    signed_client_cookie,
    verified_client_id,
)
from dau.guards import (
    _policy as _configured_policy,
)


def _policy() -> LimitPolicy:
    return LimitPolicy("test", 2, 2, 3, 1, 2, 30, 600)


def _request(*, forwarded: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded:
        headers.append((b"x-vercel-forwarded-for", forwarded.encode()))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/coach",
            "query_string": b"",
            "headers": headers,
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )
    request.state.dau_client_id = "signed-browser-id"
    return request


def test_memory_guard_enforces_cookie_and_network_windows() -> None:
    guard = InMemoryGuard(epoch_clock=lambda: 1_000.0)
    first = GuardIdentity("client-a", "network-a")
    second_client = GuardIdentity("client-b", "network-a")

    assert guard.check_window(_policy(), first).allowed is True
    assert guard.check_window(_policy(), first).allowed is True
    denied = guard.check_window(_policy(), second_client)
    assert denied.allowed is False
    assert denied.reason == "network_window"


def test_model_quota_and_lease_only_change_on_model_acquire() -> None:
    guard = InMemoryGuard(monotonic_clock=lambda: 50.0, epoch_clock=lambda: 1_000.0)
    identity = GuardIdentity("client-a", "network-a")
    policy = _policy()

    for _ in range(2):
        assert guard.check_window(policy, identity).allowed is True
    first = guard.acquire_model(policy, identity)
    assert first.allowed is True
    busy = guard.acquire_model(policy, identity)
    assert busy.reason == "client_concurrency"
    guard.release(policy, identity, first.lease_token)
    second = guard.acquire_model(policy, identity)
    assert second.allowed is True
    guard.release(policy, identity, second.lease_token)
    assert guard.acquire_model(policy, identity).reason == "client_daily"


def test_model_guard_enforces_global_daily_and_global_concurrency() -> None:
    identity_a = GuardIdentity("client-a", "network-a")
    identity_b = GuardIdentity("client-b", "network-b")

    daily_guard = InMemoryGuard(monotonic_clock=lambda: 50.0, epoch_clock=lambda: 1_000.0)
    daily_policy = LimitPolicy("daily", 10, 10, 1, 2, 2, 30)
    first = daily_guard.acquire_model(daily_policy, identity_a)
    assert first.allowed is True
    daily_guard.release(daily_policy, identity_a, first.lease_token)
    assert daily_guard.acquire_model(daily_policy, identity_b).reason == "global_daily"

    concurrency_guard = InMemoryGuard(monotonic_clock=lambda: 50.0, epoch_clock=lambda: 1_000.0)
    concurrency_policy = LimitPolicy("busy", 10, 10, 10, 2, 1, 30)
    active = concurrency_guard.acquire_model(concurrency_policy, identity_a)
    assert active.allowed is True
    assert (
        concurrency_guard.acquire_model(concurrency_policy, identity_b).reason
        == "global_concurrency"
    )


def test_cache_and_one_time_values_expire_or_consume() -> None:
    now = [10.0]
    guard = InMemoryGuard(monotonic_clock=lambda: now[0])
    guard.set("answer", "ready", 5)
    assert guard.get("answer") == "ready"
    assert guard.consume("answer") == "ready"
    assert guard.get("answer") is None
    guard.set("short", "gone", 1)
    now[0] = 12.0
    assert guard.get("short") is None


def test_upstash_window_is_atomic_across_two_identity_buckets() -> None:
    bodies: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        assert request.headers["authorization"] == "Bearer token"
        return httpx.Response(200, json={"result": ["window_allowed", 600, 19]})

    guard = UpstashGuard(
        "https://redis.example",
        "token",
        transport=httpx.MockTransport(handler),
    )
    decision = guard.check_window(_policy(), GuardIdentity("client", "network"))

    assert decision.allowed is True
    assert bodies[0][0] == "EVAL"
    assert bodies[0][1] == _WINDOW_SCRIPT
    assert bodies[0][2] == "2"
    assert bodies[0][3].endswith(":client:client")
    assert bodies[0][4].endswith(":network:network")


def test_window_lua_has_one_closer_for_each_multiline_limit_block() -> None:
    standalone_ends = [line for line in _WINDOW_SCRIPT.splitlines() if line.strip() == "end"]
    assert len(standalone_ends) == 2


def test_upstash_kill_switch_decision_is_fail_closed() -> None:
    guard = UpstashGuard(
        "https://redis.example",
        "token",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"result": ["disabled", 1, 0]})
        ),
    )
    decision = guard.acquire_model(_policy(), GuardIdentity("client", "network"))
    assert decision.allowed is False
    assert decision.reason == "disabled"


def test_policy_limits_are_environment_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAU_LIMIT_COACH_WINDOW", "9")
    monkeypatch.setenv("DAU_LIMIT_COACH_CLIENT_DAY", "11")
    monkeypatch.setenv("DAU_LIMIT_COACH_GLOBAL_DAY", "21")
    monkeypatch.setenv("DAU_LIMIT_COACH_CLIENT_CONCURRENCY", "2")
    monkeypatch.setenv("DAU_LIMIT_COACH_GLOBAL_CONCURRENCY", "5")
    policy = _configured_policy("coach", 20, 60, 300, 1, 4, 30)
    assert (
        policy.window_limit,
        policy.client_daily_limit,
        policy.global_daily_limit,
        policy.client_concurrency,
        policy.global_concurrency,
    ) == (9, 11, 21, 2, 5)


def test_signed_client_cookie_rejects_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAU_CLIENT_ID_SECRET", "test-client-secret")
    cookie, identifier = signed_client_cookie()
    assert verified_client_id(cookie) == identifier
    assert verified_client_id(cookie + "tampered") is None


def test_forwarded_network_is_trusted_only_on_vercel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAU_CLIENT_ID_SECRET", "test-client-secret")
    request = _request(forwarded="203.0.113.9")
    local = request_identity(request)
    monkeypatch.setenv("VERCEL", "1")
    deployed = request_identity(request)
    assert local.client == deployed.client
    assert local.network != deployed.network


def test_reveal_permit_is_server_owned_and_one_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = InMemoryGuard()
    request = _request()
    monkeypatch.setenv("DAU_REVEAL_SIGNING_SECRET", "test-reveal-secret")
    monkeypatch.setattr(app_module, "active_guard", lambda: guard)
    explanation = "You invited a ghost to dinner instead of your mother."

    permit = _issue_reveal_permit(request, explanation)
    assert permit is not None
    assert _read_reveal_permit(request, permit) == (
        app_module._reveal_cache_id(explanation),
        explanation,
    )
    _finish_reveal_permit(permit)
    assert _read_reveal_permit(request, permit) is None
