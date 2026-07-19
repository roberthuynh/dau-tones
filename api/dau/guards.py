"""Persistent request limits, model leases, short permits, and response caches."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

import httpx
from fastapi import Request

from .settings import (
    client_id_secret,
    is_vercel_deployment,
    upstash_redis_token,
    upstash_redis_url,
)


@dataclass(frozen=True)
class LimitPolicy:
    name: str
    window_limit: int
    client_daily_limit: int
    global_daily_limit: int | None
    client_concurrency: int | None
    global_concurrency: int | None
    lease_seconds: int
    window_seconds: int = 600


@dataclass(frozen=True)
class GuardIdentity:
    client: str
    network: str


@dataclass(frozen=True)
class GuardDecision:
    allowed: bool
    reason: str
    limit: int
    remaining: int
    retry_after: int
    backend: str
    lease_token: str | None = None


class GuardUnavailable(RuntimeError):
    """The configured persistent guard could not make a safe decision."""


class RequestGuard(Protocol):
    def check_window(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision: ...

    def acquire_model(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision: ...

    def acquire_client_day(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision: ...

    def release(
        self, policy: LimitPolicy, identity: GuardIdentity, lease_token: str | None
    ) -> None: ...

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...

    def consume(self, key: str) -> str | None: ...


def _bucket(now: float, seconds: int) -> int:
    return int(now) // seconds


class InMemoryGuard:
    """Process-local implementation for offline development and unit tests."""

    def __init__(
        self,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
        epoch_clock: Callable[[], float] = time.time,
    ) -> None:
        self._monotonic = monotonic_clock
        self._epoch = epoch_clock
        self._counts: dict[tuple[str, str, int], int] = {}
        self._windows: dict[tuple[str, str], list[float]] = {}
        self._leases: dict[tuple[str, str, str], float] = {}
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = Lock()

    @staticmethod
    def _decision(
        allowed: bool,
        reason: str,
        policy: LimitPolicy,
        remaining: int,
        retry_after: int,
        lease_token: str | None = None,
    ) -> GuardDecision:
        return GuardDecision(
            allowed,
            reason,
            policy.window_limit,
            max(0, remaining),
            max(1, retry_after),
            "memory",
            lease_token,
        )

    def check_window(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        now = self._epoch()
        keys = [
            (policy.name, f"window:client:{identity.client}"),
            (policy.name, f"window:network:{identity.network}"),
        ]
        cutoff = now - policy.window_seconds
        with self._lock:
            events = [
                [timestamp for timestamp in self._windows.get(key, []) if timestamp > cutoff]
                for key in keys
            ]
            for index, reason in ((0, "client_window"), (1, "network_window")):
                if len(events[index]) >= policy.window_limit:
                    retry = int(events[index][0] + policy.window_seconds - now + 0.999)
                    return self._decision(False, reason, policy, 0, retry)
            for key, timestamps in zip(keys, events, strict=True):
                timestamps.append(now)
                self._windows[key] = timestamps
            remaining = policy.window_limit - max(map(len, events))
        return self._decision(True, "window_allowed", policy, remaining, policy.window_seconds)

    def _daily_counts(
        self, policy: LimitPolicy, identity: GuardIdentity, day: int
    ) -> tuple[list[tuple[str, str, int]], list[int]]:
        keys = [
            (policy.name, f"day:client:{identity.client}", day),
            (policy.name, f"day:network:{identity.network}", day),
            (policy.name, "day:global", day),
        ]
        return keys, [self._counts.get(key, 0) for key in keys]

    def acquire_client_day(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        now = self._epoch()
        day = _bucket(now, 86_400)
        retry = 86_400 - int(now) % 86_400
        with self._lock:
            keys, counts = self._daily_counts(policy, identity, day)
            if counts[0] >= policy.client_daily_limit:
                return self._decision(False, "client_daily", policy, 0, retry)
            if counts[1] >= policy.client_daily_limit:
                return self._decision(False, "network_daily", policy, 0, retry)
            self._counts[keys[0]] = counts[0] + 1
            self._counts[keys[1]] = counts[1] + 1
            remaining = policy.client_daily_limit - max(counts[:2]) - 1
        return self._decision(True, "daily_allowed", policy, remaining, retry)

    def acquire_model(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        now_epoch = self._epoch()
        now = self._monotonic()
        day = _bucket(now_epoch, 86_400)
        retry = 86_400 - int(now_epoch) % 86_400
        with self._lock:
            self._leases = {key: expiry for key, expiry in self._leases.items() if expiry > now}
            keys, counts = self._daily_counts(policy, identity, day)
            if counts[0] >= policy.client_daily_limit:
                return self._decision(False, "client_daily", policy, 0, retry)
            if counts[1] >= policy.client_daily_limit:
                return self._decision(False, "network_daily", policy, 0, retry)
            if policy.global_daily_limit is not None and counts[2] >= policy.global_daily_limit:
                return self._decision(False, "global_daily", policy, 0, retry)

            client_active = sum(
                key[0] == policy.name and key[1] == f"client:{identity.client}"
                for key in self._leases
            )
            network_active = sum(
                key[0] == policy.name and key[1] == f"network:{identity.network}"
                for key in self._leases
            )
            global_active = sum(
                key[0] == policy.name and key[1] == "global" for key in self._leases
            )
            if policy.client_concurrency is not None and (
                client_active >= policy.client_concurrency
                or network_active >= policy.client_concurrency
            ):
                return self._decision(False, "client_concurrency", policy, 0, 1)
            if policy.global_concurrency is not None and global_active >= policy.global_concurrency:
                return self._decision(False, "global_concurrency", policy, 0, 1)

            self._counts[keys[0]] = counts[0] + 1
            self._counts[keys[1]] = counts[1] + 1
            if policy.global_daily_limit is not None:
                self._counts[keys[2]] = counts[2] + 1
            lease_token = None
            if policy.client_concurrency is not None or policy.global_concurrency is not None:
                lease_token = secrets.token_urlsafe(18)
                expiry = now + policy.lease_seconds
                self._leases[(policy.name, f"client:{identity.client}", lease_token)] = expiry
                self._leases[(policy.name, f"network:{identity.network}", lease_token)] = expiry
                self._leases[(policy.name, "global", lease_token)] = expiry
            remaining = policy.client_daily_limit - max(counts[:2]) - 1
        return self._decision(True, "model_allowed", policy, remaining, retry, lease_token)

    def release(
        self, policy: LimitPolicy, identity: GuardIdentity, lease_token: str | None
    ) -> None:
        if not lease_token:
            return
        with self._lock:
            self._leases.pop((policy.name, f"client:{identity.client}", lease_token), None)
            self._leases.pop((policy.name, f"network:{identity.network}", lease_token), None)
            self._leases.pop((policy.name, "global", lease_token), None)

    def get(self, key: str) -> str | None:
        now = self._monotonic()
        with self._lock:
            item = self._cache.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at <= now:
                self._cache.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            self._cache[key] = (value, self._monotonic() + ttl_seconds)

    def consume(self, key: str) -> str | None:
        now = self._monotonic()
        with self._lock:
            item = self._cache.pop(key, None)
        if item is None or item[1] <= now:
            return None
        return item[0]

    def reset(self) -> None:
        """Clear local state for isolated tests and development restarts."""

        with self._lock:
            self._counts.clear()
            self._windows.clear()
            self._leases.clear()
            self._cache.clear()


_WINDOW_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[2], '-inf', ARGV[3])
local client_count = redis.call('ZCARD', KEYS[1])
local network_count = redis.call('ZCARD', KEYS[2])
if client_count >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  local retry = math.max(1, math.ceil((tonumber(oldest[2]) - tonumber(ARGV[3])) / 1000))
  return {'client_window', retry, 0}
end
if network_count >= tonumber(ARGV[1]) then
  local oldest = redis.call('ZRANGE', KEYS[2], 0, 0, 'WITHSCORES')
  local retry = math.max(1, math.ceil((tonumber(oldest[2]) - tonumber(ARGV[3])) / 1000))
  return {'network_window', retry, 0}
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[5])
redis.call('ZADD', KEYS[2], ARGV[2], ARGV[5])
redis.call('EXPIRE', KEYS[1], ARGV[4])
redis.call('EXPIRE', KEYS[2], ARGV[4])
client_count = client_count + 1
network_count = network_count + 1
local remaining = math.max(0, tonumber(ARGV[1]) - math.max(client_count, network_count))
return {'window_allowed', tonumber(ARGV[4]), remaining}
""".strip()

_MODEL_SCRIPT = """
local enabled = redis.call('GET', KEYS[1])
if enabled == '0' or enabled == 'false' or enabled == 'off' then
  return {'disabled', 1, 0}
end
local client_day = tonumber(redis.call('GET', KEYS[2]) or '0')
local network_day = tonumber(redis.call('GET', KEYS[3]) or '0')
local global_day = tonumber(redis.call('GET', KEYS[4]) or '0')
if client_day >= tonumber(ARGV[1]) then
  return {'client_daily', math.max(1, redis.call('TTL', KEYS[2])), 0}
end
if network_day >= tonumber(ARGV[1]) then
  return {'network_daily', math.max(1, redis.call('TTL', KEYS[3])), 0}
end
if tonumber(ARGV[2]) > 0 and global_day >= tonumber(ARGV[2]) then
  return {'global_daily', math.max(1, redis.call('TTL', KEYS[4])), 0}
end
redis.call('ZREMRANGEBYSCORE', KEYS[5], '-inf', ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[6], '-inf', ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[7], '-inf', ARGV[3])
local client_active = redis.call('ZCARD', KEYS[5])
local network_active = redis.call('ZCARD', KEYS[6])
local global_active = redis.call('ZCARD', KEYS[7])
if tonumber(ARGV[4]) > 0 and
   (client_active >= tonumber(ARGV[4]) or network_active >= tonumber(ARGV[4])) then
  return {'client_concurrency', 1, 0}
end
if tonumber(ARGV[5]) > 0 and global_active >= tonumber(ARGV[5]) then
  return {'global_concurrency', 1, 0}
end
client_day = redis.call('INCR', KEYS[2])
network_day = redis.call('INCR', KEYS[3])
if client_day == 1 then redis.call('EXPIRE', KEYS[2], ARGV[7]) end
if network_day == 1 then redis.call('EXPIRE', KEYS[3], ARGV[7]) end
if tonumber(ARGV[2]) > 0 then
  global_day = redis.call('INCR', KEYS[4])
  if global_day == 1 then redis.call('EXPIRE', KEYS[4], ARGV[7]) end
end
if tonumber(ARGV[4]) > 0 or tonumber(ARGV[5]) > 0 then
  local expiry = tonumber(ARGV[3]) + tonumber(ARGV[6])
  redis.call('ZADD', KEYS[5], expiry, ARGV[8])
  redis.call('ZADD', KEYS[6], expiry, ARGV[8])
  redis.call('ZADD', KEYS[7], expiry, ARGV[8])
  redis.call('EXPIRE', KEYS[5], ARGV[6] + 5)
  redis.call('EXPIRE', KEYS[6], ARGV[6] + 5)
  redis.call('EXPIRE', KEYS[7], ARGV[6] + 5)
end
local remaining = math.max(0, tonumber(ARGV[1]) - math.max(client_day, network_day))
return {'model_allowed', math.max(1, redis.call('TTL', KEYS[2])), remaining}
""".strip()

_CLIENT_DAY_SCRIPT = """
local client_day = tonumber(redis.call('GET', KEYS[1]) or '0')
local network_day = tonumber(redis.call('GET', KEYS[2]) or '0')
if client_day >= tonumber(ARGV[1]) then
  return {'client_daily', math.max(1, redis.call('TTL', KEYS[1])), 0}
end
if network_day >= tonumber(ARGV[1]) then
  return {'network_daily', math.max(1, redis.call('TTL', KEYS[2])), 0}
end
client_day = redis.call('INCR', KEYS[1])
network_day = redis.call('INCR', KEYS[2])
if client_day == 1 then redis.call('EXPIRE', KEYS[1], ARGV[2]) end
if network_day == 1 then redis.call('EXPIRE', KEYS[2], ARGV[2]) end
local remaining = math.max(0, tonumber(ARGV[1]) - math.max(client_day, network_day))
return {'daily_allowed', math.max(1, redis.call('TTL', KEYS[1])), remaining}
""".strip()

_RELEASE_SCRIPT = """
redis.call('ZREM', KEYS[1], ARGV[1])
redis.call('ZREM', KEYS[2], ARGV[1])
redis.call('ZREM', KEYS[3], ARGV[1])
return 1
""".strip()


class UpstashGuard:
    """Atomic multi-window limits and leases over the Upstash REST surface."""

    def __init__(
        self,
        url: str,
        token: str,
        *,
        timeout: float = 2.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
            transport=transport,
        )

    def _command(self, *parts: str) -> Any:
        try:
            response = self._client.post("", json=list(parts))
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Unexpected Upstash response")
            if "error" in payload:
                raise ValueError("Upstash command failed")
            return payload.get("result")
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise GuardUnavailable("Persistent request guard unavailable") from error

    @staticmethod
    def _decision(
        result: Any, policy: LimitPolicy, lease_token: str | None = None
    ) -> GuardDecision:
        if not isinstance(result, list) or len(result) < 3:
            raise GuardUnavailable("Persistent request guard returned an invalid decision")
        reason = str(result[0])
        return GuardDecision(
            reason in {"window_allowed", "daily_allowed", "model_allowed"},
            reason,
            policy.window_limit,
            max(0, int(result[2])),
            max(1, int(result[1] or 1)),
            "upstash",
            lease_token if reason == "model_allowed" else None,
        )

    @staticmethod
    def _keys(policy: LimitPolicy, identity: GuardIdentity) -> tuple[int, int, str]:
        now = int(time.time())
        return now, now // 86_400, f"dau:ai:v1:{policy.name}"

    def check_window(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        now = int(time.time() * 1000)
        prefix = f"dau:ai:v1:rate:{policy.name}"
        token = secrets.token_urlsafe(18)
        result = self._command(
            "EVAL",
            _WINDOW_SCRIPT,
            "2",
            f"{prefix}:client:{identity.client}",
            f"{prefix}:network:{identity.network}",
            str(policy.window_limit),
            str(now),
            str(now - policy.window_seconds * 1000),
            str(policy.window_seconds + 5),
            token,
        )
        return self._decision(result, policy)

    def acquire_client_day(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        _now, day, prefix = self._keys(policy, identity)
        result = self._command(
            "EVAL",
            _CLIENT_DAY_SCRIPT,
            "2",
            f"{prefix}:day:client:{identity.client}:{day}",
            f"{prefix}:day:network:{identity.network}:{day}",
            str(policy.client_daily_limit),
            "86405",
        )
        return self._decision(result, policy)

    def acquire_model(self, policy: LimitPolicy, identity: GuardIdentity) -> GuardDecision:
        now, day, prefix = self._keys(policy, identity)
        lease_token = secrets.token_urlsafe(18)
        keys = [
            "dau:ai:enabled",
            f"{prefix}:day:client:{identity.client}:{day}",
            f"{prefix}:day:network:{identity.network}:{day}",
            f"{prefix}:day:global:{day}",
            f"{prefix}:lease:client:{identity.client}",
            f"{prefix}:lease:network:{identity.network}",
            f"{prefix}:lease:global",
        ]
        result = self._command(
            "EVAL",
            _MODEL_SCRIPT,
            str(len(keys)),
            *keys,
            str(policy.client_daily_limit),
            str(policy.global_daily_limit or 0),
            str(now),
            str(policy.client_concurrency or 0),
            str(policy.global_concurrency or 0),
            str(policy.lease_seconds),
            "86405",
            lease_token,
        )
        return self._decision(result, policy, lease_token)

    def release(
        self, policy: LimitPolicy, identity: GuardIdentity, lease_token: str | None
    ) -> None:
        if not lease_token:
            return
        prefix = f"dau:ai:v1:{policy.name}:lease"
        self._command(
            "EVAL",
            _RELEASE_SCRIPT,
            "3",
            f"{prefix}:client:{identity.client}",
            f"{prefix}:network:{identity.network}",
            f"{prefix}:global",
            lease_token,
        )

    def get(self, key: str) -> str | None:
        result = self._command("GET", key)
        return result if isinstance(result, str) else None

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._command("SET", key, value, "EX", str(ttl_seconds))

    def consume(self, key: str) -> str | None:
        result = self._command("GETDEL", key)
        return result if isinstance(result, str) else None


def _env_int(route: str, suffix: str, default: int | None) -> int | None:
    raw = os.getenv(f"DAU_LIMIT_{route.upper()}_{suffix}", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def _policy(
    name: str,
    window: int,
    client_day: int,
    global_day: int | None,
    client_concurrency: int | None,
    global_concurrency: int | None,
    lease_seconds: int,
) -> LimitPolicy:
    return LimitPolicy(
        name,
        int(_env_int(name, "WINDOW", window) or window),
        int(_env_int(name, "CLIENT_DAY", client_day) or client_day),
        _env_int(name, "GLOBAL_DAY", global_day),
        _env_int(name, "CLIENT_CONCURRENCY", client_concurrency),
        _env_int(name, "GLOBAL_CONCURRENCY", global_concurrency),
        int(_env_int(name, "LEASE_SECONDS", lease_seconds) or lease_seconds),
        int(_env_int(name, "WINDOW_SECONDS", 600) or 600),
    )


COACH_POLICY = _policy("coach", 20, 60, 300, 1, 4, 30)
DRILL_POLICY = _policy("drill", 5, 20, 80, 1, 2, 30)
TRANSCRIBE_POLICY = _policy("transcribe", 6, 20, 80, 1, 3, 60)
REVEAL_POLICY = _policy("reveal", 2, 4, 12, 1, 1, 150)
SPEAK_POLICY = _policy("speak", 30, 200, None, None, None, 0)

_MEMORY_GUARD = InMemoryGuard()
_PERSISTENT_GUARDS: dict[tuple[str, str], UpstashGuard] = {}
_PERSISTENT_LOCK = Lock()


def active_guard() -> RequestGuard:
    url = upstash_redis_url()
    token = upstash_redis_token()
    if not url or not token:
        return _MEMORY_GUARD
    key = (url, token)
    with _PERSISTENT_LOCK:
        return _PERSISTENT_GUARDS.setdefault(key, UpstashGuard(url, token))


def fallback_guard() -> InMemoryGuard:
    return _MEMORY_GUARD


def _cookie_signature(identifier: str) -> str:
    return hmac.new(client_id_secret().encode(), identifier.encode(), hashlib.sha256).hexdigest()[
        :32
    ]


def signed_client_cookie() -> tuple[str, str]:
    identifier = secrets.token_urlsafe(18)
    return f"{identifier}.{_cookie_signature(identifier)}", identifier


def verified_client_id(cookie: str | None) -> str | None:
    if not cookie or "." not in cookie:
        return None
    identifier, signature = cookie.rsplit(".", 1)
    if not identifier or not hmac.compare_digest(signature, _cookie_signature(identifier)):
        return None
    return identifier


def _subject(kind: str, value: str) -> str:
    return hmac.new(
        client_id_secret().encode(),
        f"{kind}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def request_identity(request: Request) -> GuardIdentity:
    client_id = getattr(request.state, "dau_client_id", None)
    if not isinstance(client_id, str) or not client_id:
        client_id = "missing-cookie"
    network = request.client.host if request.client else "unknown"
    if is_vercel_deployment():
        forwarded = request.headers.get("x-vercel-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            network = forwarded
    return GuardIdentity(_subject("client", client_id), _subject("network", network))


def request_subject(request: Request) -> str:
    """Compatibility helper returning the signed-cookie bucket."""

    return request_identity(request).client
