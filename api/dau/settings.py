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
AI_TIMEOUT_SECONDS = 12.0
BUILD_SPEND_TARGET_USD = 10.0
BUILD_SPEND_HARD_STOP_USD = 45.0


def openai_api_key() -> str | None:
    """Return the server-side key without caching it or exposing its value."""

    value = os.getenv("OPENAI_API_KEY", "").strip()
    return value or None


def has_openai_key() -> bool:
    return openai_api_key() is not None
