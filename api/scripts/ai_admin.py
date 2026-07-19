"""Inspect or change Dấu's production AI kill switch.

Usage from the repository root:
    uv run --project api python -m scripts.ai_admin status
    uv run --project api python -m scripts.ai_admin disable
    uv run --project api python -m scripts.ai_admin enable
"""

from __future__ import annotations

import argparse
from typing import Literal

import httpx

from dau.settings import upstash_redis_token, upstash_redis_url

Action = Literal["status", "enable", "disable"]
KILL_SWITCH_KEY = "dau:ai:enabled"


def change_ai_state(
    action: Action,
    *,
    url: str,
    token: str,
    transport: httpx.BaseTransport | None = None,
) -> str:
    command = ["GET", KILL_SWITCH_KEY]
    if action != "status":
        command = ["SET", KILL_SWITCH_KEY, "1" if action == "enable" else "0"]
    try:
        with httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=5.0,
            transport=transport,
        ) as client:
            response = client.post("", json=command)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise RuntimeError("Could not update the Dấu AI guard") from error
    if not isinstance(payload, dict) or payload.get("error"):
        raise RuntimeError("Upstash rejected the Dấu AI guard command")
    if action == "status":
        disabled = str(payload.get("result", "1")).lower() in {"0", "false", "off"}
        return "disabled" if disabled else "enabled"
    return "enabled" if action == "enable" else "disabled"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "enable", "disable"))
    args = parser.parse_args()
    url = upstash_redis_url()
    token = upstash_redis_token()
    if not url or not token:
        raise SystemExit("KV_REST_API_URL and KV_REST_API_TOKEN are required")
    state = change_ai_state(args.action, url=url, token=token)
    print(f"Dấu AI is {state}.")


if __name__ == "__main__":
    main()
