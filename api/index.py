"""Vercel Services entrypoint for the FastAPI application."""

from __future__ import annotations

import sys
from pathlib import Path

# Vercel installs this project into ``_vendor`` and may restore that wheel from
# a dependency cache even when application source changed. The checked-in API
# directory must win so the deployed function always runs the current commit.
API_SOURCE = str(Path(__file__).resolve().parent)
if API_SOURCE in sys.path:
    sys.path.remove(API_SOURCE)
sys.path.insert(0, API_SOURCE)

from dau.app import app  # noqa: E402

__all__ = ["app"]
