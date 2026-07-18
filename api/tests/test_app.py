from __future__ import annotations

import io
import wave

import numpy as np
from fastapi.testclient import TestClient

from dau.app import app

client = TestClient(app, raise_server_exceptions=False)


def _wav(samples: np.ndarray, sample_rate: int = 22_050) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        pcm = np.clip(samples, -1.0, 1.0)
        handle.writeframes((pcm * 32767).astype("<i2").tobytes())
    return output.getvalue()


def test_health_exposes_offline_capabilities(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["capabilities"]["local_dsp"] is True
    assert payload["capabilities"]["ai_coaching"] is False
    assert payload["banner"] == "Add an OpenAI key for AI coaching"


def test_words_starts_with_phuong_and_has_64_point_targets() -> None:
    payload = client.get("/words").json()
    assert payload["featured_queue"][:3] == [
        "phuong-name",
        "phuong-ward",
        "phuong-phoenix",
    ]
    phuong = next(item for item in payload["words"] if item["id"] == "phuong-name")
    assert phuong["surface"] == "Phương"
    assert len(phuong["targets"]["north"]["contour"]) == 64
    assert len(phuong["targets"]["south"]["contour"]) == 64


def test_silent_upload_returns_human_retry_error() -> None:
    response = client.post(
        "/analyze",
        files={"audio": ("silence.wav", _wav(np.zeros(22_050)), "audio/wav")},
        data={"word": "ma-mother", "intended_tone": "sac", "accent": "north"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "silence"
    assert detail["needs_retry"] is True


def test_unknown_word_is_rejected_without_analysis() -> None:
    time = np.arange(11_025) / 22_050
    voice = 0.2 * np.sin(2 * np.pi * 180 * time)
    response = client.post(
        "/analyze",
        files={"audio": ("voice.wav", _wav(voice), "audio/wav")},
        data={"word": "not-a-word", "intended_tone": "sac"},
    )
    assert response.status_code == 400


def test_offline_coach_is_specific(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/coach",
        json={
            "verdict": {
                "word": "ma-mother",
                "tone_intended": "sac",
                "correct": False,
                "tips_features": {"codes": ["no_final_rise"]},
            },
            "history": [],
            "accent": "south",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "lift" in payload["coaching_sentence"].lower()
    assert payload["source"] == "rules"
    assert payload["next_word"]
    assert payload["rationale"].startswith("because")


def test_offline_echo_demo_closes_transcript_loop(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/echo/transcribe",
        data={
            "sentence_id": "invite-mom-to-dinner",
            "demo_id": "invite-mom-said-ghost",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "fixture"
    assert any(item["kind"] == "tone" for item in payload["diff"])
    assert "ghost" in payload["explanation"]


def test_arbitrary_offline_echo_explains_requirement(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/echo/transcribe",
        data={"sentence_id": "xin-chao"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "echo_live_requires_key"
