"""Runtime settings and repository paths.

All OpenAI access stays server-side. Importing this module never creates a
client or requires a key, which keeps the offline product path cold-start safe.
"""

from __future__ import annotations

import os
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = API_ROOT.parent
# Vercel installs ``dau`` into ``_vendor`` before importing the checked-in
# entrypoint. Repository assets still live beside ``api/index.py``, so resolve
# data from the repository root instead of beside the installed package.
DATA_ROOT = REPO_ROOT / "api" / "data"
TARGETS_ROOT = REPO_ROOT / "targets"
FIXTURES_ROOT = REPO_ROOT / "fixtures"
WEB_PUBLIC_ROOT = REPO_ROOT / "web" / "public"

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = 12 * 1024 * 1024
AI_TIMEOUT_SECONDS = 18.0
BUILD_SPEND_TARGET_USD = 10.0
BUILD_SPEND_HARD_STOP_USD = 45.0


def openai_api_key() -> str | None:
    """Return the server-side key without caching it or exposing its value."""

    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def has_openai_key() -> bool:
    return openai_api_key() is not None


def upstash_redis_url() -> str | None:
    """Return the Vercel Marketplace Upstash REST endpoint when configured."""

    value = (
        os.getenv("KV_REST_API_URL", "").strip() or os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
    ).rstrip("/")
    return value or None


def upstash_redis_token() -> str | None:
    value = (
        os.getenv("KV_REST_API_TOKEN", "").strip()
        or os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()
    )
    return value or None


def has_persistent_guard() -> bool:
    return bool(upstash_redis_url() and upstash_redis_token())


def guard_hash_secret() -> str:
    """Return a one-way subject hashing secret without exposing client addresses."""

    return (
        os.getenv("DAU_GUARD_HASH_SECRET", "").strip()
        or os.getenv("VERCEL_PROJECT_ID", "").strip()
        or openai_api_key()
        or "dau-local-rate-guard-v1"
    )


def client_id_secret() -> str:
    """Secret used to sign the anonymous, HTTP-only rate-limit identity."""

    return os.getenv("DAU_CLIENT_ID_SECRET", "").strip() or guard_hash_secret()


def has_explicit_client_id_secret() -> bool:
    return bool(os.getenv("DAU_CLIENT_ID_SECRET", "").strip())


def guard_mode() -> str:
    value = os.getenv("DAU_GUARD_MODE", "local").strip().lower()
    return value if value in {"local", "strict"} else "strict"


def is_vercel_deployment() -> bool:
    return os.getenv("VERCEL", "").strip() == "1" or os.getenv(
        "VERCEL_ENV", ""
    ).strip().lower() in {"production", "preview"}


def reveal_signing_secret() -> str:
    """Sign image jobs so a browser cannot turn the route into an open prompt API."""

    return (
        os.getenv("DAU_REVEAL_SIGNING_SECRET", "").strip()
        or openai_api_key()
        or "dau-local-reveal-v1"
    )


def guard_fail_closed() -> bool:
    """Protect paid routes if the configured persistent guard cannot be reached."""

    return os.getenv("DAU_GUARD_FAIL_CLOSED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
