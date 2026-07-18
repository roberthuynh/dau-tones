from __future__ import annotations

import pathlib
import re

from dau import models


def test_active_model_registry_is_exact() -> None:
    assert models.ACTIVE_MODELS == {
        "text": "gpt-5.6-sol",
        "image": "gpt-image-2",
        "transcription": "gpt-4o-transcribe",
        "speech": "gpt-realtime-2.1-mini",
        "reference": "gpt-realtime-2.1",
    }


def test_deprecated_tts_is_not_active() -> None:
    assert all("mini-tts" not in model for model in models.ACTIVE_MODELS.values())


def test_ci_model_guard_checks_active_code_but_allows_test_fixtures() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    roots = [
        repo_root / "api/dau",
        repo_root / "api/scripts",
        repo_root / "api/index.py",
        repo_root / "api/eval.py",
        repo_root / "web/src",
    ]
    found: set[str] = set()
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if path.suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
                found.update(
                    re.findall(
                        r"gpt-[a-z0-9][a-z0-9.\-]*",
                        path.read_text(encoding="utf-8"),
                    )
                )

    assert found <= set(models.ACTIVE_MODELS.values())
    assert "gpt-4o-mini-tts" not in found
    assert "gpt-4o-mini-tts" in (
        repo_root / "api/tests/test_inventory.py"
    ).read_text(encoding="utf-8")
