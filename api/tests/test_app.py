from __future__ import annotations

import io
import json
import logging
import wave
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient

from dau import app as app_module
from dau.app import _reveal_cache_id, _validated_audio_duration, app
from dau.guards import GuardDecision, GuardUnavailable, InMemoryGuard, fallback_guard
from dau.schemas import CoachResponse

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_local_guard() -> None:
    fallback_guard().reset()
    client.cookies.clear()


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
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["permissions-policy"].startswith("microphone=(self)")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-request-id"]
    assert response.cookies.get("dau_client")


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


def test_words_starts_with_all_six_ma_forms_and_has_64_point_targets() -> None:
    payload = client.get("/words").json()
    assert payload["featured_queue"][:6] == [
        "ma-ghost",
        "ma-but",
        "ma-mother",
        "ma-grave",
        "ma-code",
        "ma-seedling",
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
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_request"
    assert any(item["location"][-1] == "intended_tone" for item in detail["issues"])


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
    assert "measurable shape difference" in payload["observation"]
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


def test_coach_rejects_unbounded_history_and_verdicts(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    oversized_verdict = client.post(
        "/coach",
        json={"verdict": {"blob": "x" * 17_000}},
    )
    oversized_history = client.post(
        "/coach",
        json={
            "verdict": {"word": "ma-ghost"},
            "history": [{"blob": "x" * 2_100}],
        },
    )

    assert oversized_verdict.status_code == 422
    assert oversized_history.status_code == 422
    assert oversized_verdict.json()["detail"]["code"] == "invalid_request"


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


def test_echo_scenes_expose_four_linked_dialogues_and_static_audio() -> None:
    response = client.get("/echo/scenes")
    assert response.status_code == 200
    payload = response.json()
    assert [scene["id"] for scene in payload["scenes"]] == [
        "meet-family",
        "family-dinner",
        "pho-shop",
        "around-ward",
    ]
    turns = [turn for scene in payload["scenes"] for turn in scene["turns"]]
    assert len(turns) == 26
    assert sum(turn["speaker"] == "learner" for turn in turns) == 13
    assert turns[0]["id"] == "meet-family-minh-01"
    assert turns[0]["audio_urls"]["north"] == ("/audio/echo/north/meet-family-minh-01.wav")
    assert all(len(turn["focuses"]) >= 1 for turn in turns)


def test_echo_sentences_remains_a_learner_turn_compatibility_alias() -> None:
    response = client.get("/echo/sentences")
    assert response.status_code == 200
    sentences = response.json()["sentences"]
    assert len(sentences) == 13
    assert all(item["speaker"] == "learner" for item in sentences)
    assert all(item["sentence_id"] == item["id"] for item in sentences)
    assert all(item["text"] != "Xin chào!" for item in sentences)


def test_scene_demo_returns_navigation_tones_and_practice_ids(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/echo/transcribe",
        data={
            "turn_id": "meet-family-learner-01",
            "demo_id": "meet-family-said-ghost",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scene_id"] == "meet-family"
    assert payload["turn_id"] == payload["sentence_id"] == "meet-family-learner-01"
    assert payload["next_turn_id"] == "meet-family-minh-02"
    assert payload["practice_word_ids"] == ["ma-mother"]
    assert payload["meaning_status"] == "known_word_change"
    assert payload["detected_tones"] == [
        {
            "token_index": 10,
            "target": "má",
            "heard": "ma",
            "intended_tone": "sac",
            "detected_tone": "ngang",
            "target_word_id": "ma-mother",
            "heard_word_id": "ma-ghost",
            "semantic_status": "known_word",
        }
    ]


def test_scene_transcribe_accepts_sentence_id_alias(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post(
        "/echo/transcribe",
        data={
            "sentence_id": "family-dinner-learner-03",
            "demo_id": "family-dinner-seedling-code",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["scene_id"] == "family-dinner"
    assert payload["turn_id"] == "family-dinner-learner-03"
    assert payload["meaning_status"] == "known_word_change"
    assert payload["practice_word_ids"] == ["ma-code"]


def test_keyed_echo_demo_never_creates_a_live_reveal_permit(monkeypatch) -> None:
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
    assert payload["reveal_id"] is None


def test_offline_echo_demo_bypasses_the_paid_guard(monkeypatch) -> None:
    class BrokenGuard(InMemoryGuard):
        def check_window(self, *_args, **_kwargs):
            raise GuardUnavailable("offline")

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("DAU_GUARD_MODE", "strict")
    monkeypatch.setattr(app_module, "active_guard", lambda: BrokenGuard())

    response = client.post(
        "/echo/transcribe",
        data={
            "turn_id": "meet-family-learner-01",
            "demo_id": "meet-family-said-ghost",
        },
    )

    assert response.status_code == 200
    assert response.json()["source"] == "fixture"


def test_live_echo_rejects_invalid_audio_before_model_quota(monkeypatch) -> None:
    class TrackingGuard(InMemoryGuard):
        model_acquires = 0

        def acquire_model(self, policy, identity):
            self.model_acquires += 1
            return super().acquire_model(policy, identity)

    guard = TrackingGuard()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(app_module, "active_guard", lambda: guard)

    unsupported = client.post(
        "/echo/transcribe",
        files={"audio": ("take.txt", b"not audio", "text/plain")},
        data={"turn_id": "meet-family-learner-01"},
    )
    corrupt = client.post(
        "/echo/transcribe",
        files={"audio": ("take.webm", b"not audio", "audio/webm;codecs=opus")},
        data={"turn_id": "meet-family-learner-01"},
    )

    assert unsupported.status_code == 415
    assert unsupported.json()["detail"]["code"] == "unsupported_audio_type"
    assert corrupt.status_code == 422
    assert corrupt.json()["detail"]["code"] == "invalid_audio"
    assert guard.model_acquires == 0


def test_echo_transcription_rejects_ambiguous_or_partner_inputs(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    both_ids = client.post(
        "/echo/transcribe",
        data={
            "turn_id": "meet-family-learner-01",
            "sentence_id": "meet-family-learner-01",
        },
    )
    demo_and_audio = client.post(
        "/echo/transcribe",
        files={"audio": ("take.wav", _wav(np.zeros(22_050)), "audio/wav")},
        data={
            "turn_id": "meet-family-learner-01",
            "demo_id": "meet-family-said-ghost",
        },
    )
    partner = client.post(
        "/echo/transcribe",
        files={"audio": ("take.wav", _wav(np.zeros(22_050)), "audio/wav")},
        data={"turn_id": "meet-family-minh-01"},
    )

    assert both_ids.status_code == 400
    assert demo_and_audio.status_code == 400
    assert partner.status_code == 400
    assert partner.json()["detail"]["code"] == "learner_turn_required"


def test_dialogue_audio_duration_bounds() -> None:
    short = _wav(np.zeros(int(22_050 * 0.2)))
    long = _wav(np.zeros(int(22_050 * 30.2)))

    with pytest.raises(app_module.RouteError, match="third of a second") as too_short:
        _validated_audio_duration(short)
    with pytest.raises(app_module.RouteError, match="under 30 seconds") as too_long:
        _validated_audio_duration(long)

    assert too_short.value.code == "audio_too_short"
    assert too_long.value.code == "audio_too_long"


def test_live_echo_transcription_accepts_a_bounded_learner_take(monkeypatch) -> None:
    target = next(
        sentence
        for sentence in client.get("/echo/sentences").json()["sentences"]
        if sentence["id"] == "meet-family-learner-01"
    )["text"]

    class Transcriptions:
        @staticmethod
        def create(**_kwargs):
            return target

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        app_module,
        "_openai_client",
        lambda *_args, **_kwargs: SimpleNamespace(
            audio=SimpleNamespace(transcriptions=Transcriptions())
        ),
    )
    take = _wav(0.1 * np.sin(2 * np.pi * 180 * np.arange(22_050) / 22_050))

    response = client.post(
        "/echo/transcribe",
        files={"audio": ("take.wav", take, "audio/wav")},
        data={"turn_id": "meet-family-learner-01"},
    )

    assert response.status_code == 200
    assert response.json()["meaning_status"] == "exact_match"
    assert response.json()["reveal_id"] is None


def test_echo_reveal_returns_webp_directly_and_reuses_persistent_cache(monkeypatch) -> None:
    explanation = "You invited a ghost to dinner instead of your mother."
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    image_id = _reveal_cache_id(explanation)
    reveal_id = f"{'a' * 20}.{'b' * 24}"
    generated: list[str] = []
    image = b"RIFFcommitted-test-imageWEBP"
    guard = InMemoryGuard()
    monkeypatch.setattr(app_module, "active_guard", lambda: guard)
    monkeypatch.setattr(
        "dau.app._read_reveal_permit",
        lambda *_args: (image_id, explanation),
    )
    monkeypatch.setattr("dau.app._finish_reveal_permit", lambda *_args: None)
    monkeypatch.setattr(
        "dau.app._generate_reveal",
        lambda value: generated.append(value) or image,
    )
    first = client.post(
        f"/echo/reveals/{reveal_id}",
    )
    second = client.post(
        f"/echo/reveals/{reveal_id}",
    )

    assert first.status_code == second.status_code == 200
    assert first.headers["content-type"] == "image/webp"
    assert first.headers["cache-control"] == "public, max-age=86400"
    assert first.content == second.content == image
    assert generated == [explanation]


def test_echo_reveal_rejects_a_prompt_mismatch_before_generation(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("dau.app._read_reveal_permit", lambda *_args: None)
    monkeypatch.setattr(
        "dau.app._generate_reveal",
        lambda _explanation: (_ for _ in ()).throw(AssertionError("generated mismatched art")),
    )

    response = client.post(
        "/echo/reveals/not-the-prompt-hash",
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_reveal"


def test_echo_explanation_sends_only_changed_tokens_without_storage(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Responses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                output_parsed=app_module.EchoExplanation(
                    explanation="You invited a ghost instead of your mother."
                )
            )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        app_module,
        "_openai_client",
        lambda *_args, **_kwargs: SimpleNamespace(responses=Responses()),
    )
    result = app_module._ai_explanation(
        [
            {"target": "tôi", "heard": "tôi", "kind": "match"},
            {
                "target": "má",
                "heard": "ma",
                "kind": "tone_only",
                "target_tone": "sac",
                "heard_tone": "ngang",
                "semantic_status": "known_word",
                "meaning_explanation": "ghost instead of mother",
                "target_index": 4,
            },
        ],
        "You said ghost instead of mother.",
        "hashed-client-id",
    )
    evidence = json.loads(captured["input"][1]["content"])
    assert len(evidence["changed_tokens"]) == 1
    assert evidence["changed_tokens"][0]["heard"] == "ma"
    assert "target_index" not in evidence["changed_tokens"][0]
    assert captured["store"] is False
    assert captured["safety_identifier"] == "hashed-client-id"
    assert "ghost" in result


def test_request_log_uses_route_template_not_reveal_token(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    token = "private-one-time-reveal-token"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(app_module, "_read_reveal_permit", lambda *_args: None)
    caplog.set_level(logging.INFO, logger="dau.api")
    response = client.post(f"/echo/reveals/{token}")
    assert response.status_code == 400
    record = next(item.message for item in caplog.records if "http_request" in item.message)
    assert '"endpoint":"/echo/reveals/{reveal_id}"' in record
    assert token not in record


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
        label in response.headers["server-timing"] for label in ("pitch;dur=", "pitch_fast;dur=")
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
    assert payload["semantic_status"] == "wrong_known_word"
    assert payload["class_confidence"] == payload["confidence"]
    assert payload["signal_confidence"] > 0.35
    assert payload["meaning_verdict"] == {
        "status": "wrong_known_word",
        "assertion_level": "family",
        "detected_surface": "phường",
        "detected_meaning_en": "urban ward",
        "detected_word_id": "phuong-ward",
        "tone_mark_label": "dấu huyền",
    }
    assert payload["classifier_version"].startswith("dau-")
    assert len(payload["classifier_manifest_hash"]) == 64
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


def test_echo_speech_only_serves_committed_turns() -> None:
    seeded = client.post(
        "/echo/speak",
        json={"turn_id": "meet-family-learner-02", "accent": "north"},
    )
    assert seeded.status_code == 200
    assert seeded.headers["content-type"] == "audio/wav"

    arbitrary = client.post(
        "/echo/speak",
        json={"text": "Say anything a caller supplied", "accent": "north"},
    )
    both = client.post(
        "/echo/speak",
        json={
            "turn_id": "meet-family-learner-02",
            "sentence_id": "meet-family-learner-02",
            "accent": "north",
        },
    )
    assert arbitrary.status_code == 422
    assert both.status_code == 422
    assert arbitrary.json()["detail"]["code"] == "invalid_request"


def test_production_paid_route_requires_botid_assertion(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    response = client.post(
        "/coach",
        json={"verdict": {"word": "ma-ghost", "correct": True}},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "bot_blocked"


def test_strict_production_fails_closed_without_persistent_guard(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("DAU_GUARD_MODE", "strict")
    monkeypatch.setenv("DAU_CLIENT_ID_SECRET", "test-client-secret")
    response = client.post(
        "/coach",
        headers={"x-dau-bot-verified": "1"},
        json={"verdict": {"word": "ma-ghost", "correct": True}},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_guard_unavailable"


def test_strict_production_fails_closed_when_redis_is_unavailable(monkeypatch) -> None:
    class BrokenGuard(InMemoryGuard):
        def check_window(self, *_args, **_kwargs):
            raise GuardUnavailable("offline")

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("DAU_GUARD_MODE", "strict")
    monkeypatch.setenv("DAU_CLIENT_ID_SECRET", "test-client-secret")
    monkeypatch.setenv("KV_REST_API_URL", "https://redis.example")
    monkeypatch.setenv("KV_REST_API_TOKEN", "token")
    monkeypatch.setattr(app_module, "active_guard", lambda: BrokenGuard())
    response = client.post(
        "/coach",
        headers={"x-dau-bot-verified": "1"},
        json={"verdict": {"word": "ma-ghost", "correct": True}},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "ai_guard_unavailable"


@pytest.mark.parametrize(
    ("reason", "expected_code"),
    [
        ("client_window", "ai_rate_limited"),
        ("client_daily", "ai_daily_limit"),
        ("global_concurrency", "ai_busy"),
        ("disabled", "ai_paused"),
    ],
)
def test_paid_guard_decisions_return_typed_errors(
    monkeypatch, reason: str, expected_code: str
) -> None:
    class DenyingGuard(InMemoryGuard):
        def check_window(self, policy, identity):
            if reason == "client_window":
                return GuardDecision(False, reason, policy.window_limit, 0, 9, "memory")
            return super().check_window(policy, identity)

        def acquire_model(self, policy, identity):
            return GuardDecision(False, reason, policy.window_limit, 0, 9, "memory")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(app_module, "active_guard", lambda: DenyingGuard())

    response = client.post(
        "/coach",
        json={"verdict": {"word": "ma-ghost", "correct": False}},
    )

    assert response.status_code in {429, 503}
    assert response.json()["detail"]["code"] == expected_code
    if response.status_code == 429:
        assert response.headers["retry-after"] == "9"


def test_cached_coach_skips_a_second_model_quota(monkeypatch) -> None:
    class TrackingGuard(InMemoryGuard):
        model_acquires = 0

        def acquire_model(self, policy, identity):
            self.model_acquires += 1
            return super().acquire_model(policy, identity)

    guard = TrackingGuard()
    generated = 0

    def refined(*_args, **_kwargs):
        nonlocal generated
        generated += 1
        return CoachResponse(
            observation="Your ending landed below the target.",
            coaching_sentence="Keep your chin level through the vowel.",
            next_word="ma-ghost",
            rationale="because the level shape needs another repetition",
            source="gpt-5.6-sol",
            refinement_status="complete",
        )

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(app_module, "active_guard", lambda: guard)
    monkeypatch.setattr(app_module, "coach", refined)
    payload = {"verdict": {"word": "ma-ghost", "correct": False}}
    first = client.post("/coach", json=payload)
    second = client.post("/coach", json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()["refinement_status"] == "cache_hit"
    assert guard.model_acquires == generated == 1


def test_model_lease_releases_when_route_work_raises(monkeypatch) -> None:
    class TrackingGuard(InMemoryGuard):
        releases = 0

        def release(self, policy, identity, lease_token):
            self.releases += 1
            super().release(policy, identity, lease_token)

    guard = TrackingGuard()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(app_module, "active_guard", lambda: guard)
    monkeypatch.setattr(
        app_module,
        "coach",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("provider exploded")),
    )
    response = client.post(
        "/coach",
        json={"verdict": {"word": "ma-ghost", "correct": False}},
    )
    assert response.status_code == 500
    assert guard.releases == 1
