from __future__ import annotations

import io
import wave

import numpy as np
from fastapi.testclient import TestClient

from dau.app import REVEAL_CACHE, REVEAL_GENERATION_LOCKS, _reveal_cache_id, app

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
    assert payload["reference_corpus_validated"] is False


def test_analysis_warmup_reports_timing_and_is_idempotent(monkeypatch) -> None:
    calls = 0

    def warm(timing: dict[str, float]) -> bool:
        nonlocal calls
        calls += 1
        timing["runtime_wait"] = 0.25
        timing["pitch_warmup"] = 8.5
        return calls == 1

    monkeypatch.setattr("dau.app.warm_analysis_runtime", warm)

    first = client.post("/analysis/warmup")
    second = client.post("/analysis/warmup")

    assert first.status_code == second.status_code == 200
    assert first.json() == {"status": "ready", "cold_started": True}
    assert second.json() == {"status": "ready", "cold_started": False}
    assert "runtime_wait;dur=0.25" in first.headers["server-timing"]
    assert "pitch_warmup;dur=8.50" in first.headers["server-timing"]


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
    assert payload["scoring_modes"] == client.get("/healthz").json()["scoring_modes"]


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


def test_analyze_requires_intended_tone_before_processing_audio() -> None:
    response = client.post(
        "/analyze",
        files={"audio": ("silence.wav", _wav(np.zeros(22_050)), "audio/wav")},
        data={"word": "ma-mother", "accent": "north"},
    )
    assert response.status_code == 422
    assert any(item["loc"][-1] == "intended_tone" for item in response.json()["detail"])


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


def test_offline_coach_uses_public_tone_intended_history_name(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/coach",
        json={
            "verdict": {"word": "phuong-name", "tone_intended": "ngang", "correct": True},
            "history": [
                {"tone_intended": "hoi", "correct": False},
                {"tone_intended": "hoi", "correct": False},
                {"tone_intended": "sac", "correct": False},
            ],
            "accent": "north",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["next_word"] == "ma-grave"
    assert "hoi" in payload["rationale"]


def test_offline_coach_accepts_legacy_intended_tone_history_name(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/coach",
        json={
            "verdict": {"word": "phuong-name", "tone_intended": "ngang", "correct": True},
            "history": [{"intended_tone": "nang", "correct": False}],
            "accent": "north",
        },
    )
    assert response.status_code == 200
    assert response.json()["next_word"] == "ma-seedling"


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
    assert any(item["kind"] == "tone_only" for item in payload["diff"])
    assert payload["target_text"] == payload["target"]
    assert payload["tokens"] == payload["diff"]
    assert "ghost" in payload["literal_explanation"]
    assert "ghost" in payload["explanation"]


def test_keyed_echo_returns_a_reveal_id_without_background_generation(monkeypatch) -> None:
    explanation = "You invited a ghost to dinner instead of your mother."
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("dau.app._ai_explanation", lambda *_args: explanation)
    monkeypatch.setattr(
        "dau.app._generate_reveal",
        lambda _explanation: (_ for _ in ()).throw(AssertionError("generated in transcribe")),
    )

    response = client.post(
        "/echo/transcribe",
        data={
            "sentence_id": "invite-mom-to-dinner",
            "demo_id": "invite-mom-said-ghost",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reveal_id"] == _reveal_cache_id(payload["literal_explanation"])


def test_echo_reveal_returns_png_directly_and_reuses_warm_cache(monkeypatch) -> None:
    explanation = "You invited a ghost to dinner instead of your mother."
    reveal_id = _reveal_cache_id(explanation)
    generated: list[str] = []
    png = b"\x89PNG\r\n\x1a\ncommitted-test-image"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "dau.app._generate_reveal",
        lambda value: generated.append(value) or png,
    )
    REVEAL_CACHE.pop(reveal_id, None)
    REVEAL_GENERATION_LOCKS.pop(reveal_id, None)

    first = client.post(
        f"/echo/reveals/{reveal_id}",
        json={"explanation": explanation},
    )
    second = client.post(
        f"/echo/reveals/{reveal_id}",
        json={"explanation": explanation},
    )

    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert first.content == second.content == png
    assert generated == [explanation]
    REVEAL_CACHE.pop(reveal_id, None)
    REVEAL_GENERATION_LOCKS.pop(reveal_id, None)


def test_echo_reveal_rejects_a_prompt_mismatch_before_generation(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "dau.app._generate_reveal",
        lambda _explanation: (_ for _ in ()).throw(AssertionError("generated mismatched art")),
    )

    response = client.post(
        "/echo/reveals/not-the-prompt-hash",
        json={"explanation": "You invited a ghost to dinner instead of your mother."},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_reveal"


def test_signature_audio_demo_runs_through_validated_partial_templates(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    sample = client.get("/demos/phuong-name-said-ward.wav")
    assert sample.status_code == 200

    response = client.post(
        "/analyze",
        files={"audio": ("phuong-ward.wav", sample.content, "audio/wav")},
        data={
            "word": "phuong-name",
            "intended_tone": "ngang",
            "accent": "north",
        },
    )

    assert response.status_code == 200
    assert "decode;dur=" in response.headers["server-timing"]
    assert any(
        label in response.headers["server-timing"]
        for label in ("pitch;dur=", "pitch_fast;dur=")
    )
    assert "classify;dur=" in response.headers["server-timing"]
    assert "total;dur=" in response.headers["server-timing"]
    payload = response.json()
    assert payload["tone_detected"] == "huyen"
    assert payload["intended_word_id"] == "phuong-name"
    assert payload["detected_word_id"] == "phuong-ward"
    assert len(payload["detected_contour"]) == 64
    assert payload["family_verified"] is True
    assert payload["exact_verified"] is False
    assert payload["alternatives"]
    assert all("confidence" in item for item in payload["alternatives"])
    assert payload["detected_word"]["id"] == "phuong-ward"
    assert payload["verdict_copy"] == (
        "You meant Phương, the name. You said phường, an urban ward."
    )


def test_arbitrary_offline_echo_explains_requirement(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/echo/transcribe",
        data={"sentence_id": "xin-chao"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "echo_live_requires_key"
