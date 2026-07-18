"""Build-time cost ledger with a non-bypassable hard stop."""

from __future__ import annotations

import fcntl
import json
from datetime import UTC, datetime
from typing import Any

from .settings import BUILD_SPEND_HARD_STOP_USD, BUILD_SPEND_TARGET_USD, REPO_ROOT

LEDGER_PATH = REPO_ROOT / ".cache" / "spend_ledger.json"
LOCK_PATH = REPO_ROOT / ".cache" / "spend_ledger.lock"


def load_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return {"estimated_total_usd": 0.0, "events": []}
    return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))


def approve(projected_usd: float, label: str) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = load_ledger()
        current = float(ledger.get("estimated_total_usd", 0.0))
        projected = current + projected_usd
        fcntl.flock(lock, fcntl.LOCK_UN)
    print(
        f"{label}: estimated ${projected_usd:.2f}; build ledger would be ${projected:.2f} "
        f"(target <${BUILD_SPEND_TARGET_USD:.0f}, hard stop ${BUILD_SPEND_HARD_STOP_USD:.0f})"
    )
    if projected > BUILD_SPEND_HARD_STOP_USD:
        raise RuntimeError("Build spend hard stop reached; refusing the API call")


def record(label: str, estimated_usd: float, usage: dict[str, Any] | None = None) -> None:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        ledger = load_ledger()
        projected = float(ledger.get("estimated_total_usd", 0.0)) + estimated_usd
        if projected > BUILD_SPEND_HARD_STOP_USD:
            raise RuntimeError("Build spend hard stop reached; refusing to record another API call")
        normalized_usage = usage or {}
        if hasattr(normalized_usage, "model_dump"):
            normalized_usage = normalized_usage.model_dump()
        ledger.setdefault("events", []).append(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "label": label,
                "estimated_usd": round(estimated_usd, 6),
                "usage": normalized_usage,
            }
        )
        ledger["estimated_total_usd"] = round(projected, 6)
        temporary = LEDGER_PATH.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(ledger, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        temporary.replace(LEDGER_PATH)
        fcntl.flock(lock, fcntl.LOCK_UN)
