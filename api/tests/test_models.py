from __future__ import annotations

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
