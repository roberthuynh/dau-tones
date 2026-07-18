from __future__ import annotations

import numpy as np
import soundfile as sf

from dau.models import REFERENCE_MODEL, SPEECH_MODEL
from dau.realtime_audio import _usable_incomplete_audio
from scripts import gen_echo_audio


def test_echo_contour_quality_accepts_clear_voiced_audio(tmp_path) -> None:
    sample_rate = 24_000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    samples = 0.2 * np.sin(2 * np.pi * 180 * time)
    path = tmp_path / "voice.wav"
    sf.write(path, samples, sample_rate, subtype="PCM_16")

    quality = gen_echo_audio._contour_quality(path)

    assert quality["passed"] is True
    assert quality["voiced_fraction"] >= 0.15


def test_echo_generation_steps_up_only_after_failed_validation(monkeypatch, tmp_path) -> None:
    destination = tmp_path / "sentence.wav"

    def synthesize(_text: str, *, accent: str, model: str) -> bytes:
        assert accent == "north"
        return model.encode()

    def validate(path, _text: str):
        return {
            "passed": path.read_bytes() == REFERENCE_MODEL.encode(),
            "transcript": "Xin chào",
        }

    monkeypatch.setattr(gen_echo_audio, "synthesize_utterance", synthesize)
    monkeypatch.setattr(gen_echo_audio, "_validate", validate)
    monkeypatch.setattr(gen_echo_audio, "record", lambda *_args, **_kwargs: None)

    selected, receipt = gen_echo_audio._generate_validated("Xin chào!", "north", destination)

    assert selected == REFERENCE_MODEL
    assert destination.read_bytes() == REFERENCE_MODEL.encode()
    assert [attempt["model"] for attempt in receipt["attempts"]] == [
        SPEECH_MODEL,
        REFERENCE_MODEL,
    ]


def test_only_token_capped_audio_can_enter_the_target_validation_gate() -> None:
    token_capped = {
        "status": "incomplete",
        "status_details": {"reason": "max_output_tokens"},
    }

    assert _usable_incomplete_audio(token_capped, allow_incomplete_audio=True, has_audio=True)
    assert not _usable_incomplete_audio(token_capped, allow_incomplete_audio=False, has_audio=True)
    assert not _usable_incomplete_audio(token_capped, allow_incomplete_audio=True, has_audio=False)
    assert not _usable_incomplete_audio(
        {
            "status": "incomplete",
            "status_details": {"reason": "content_filter"},
        },
        allow_incomplete_audio=True,
        has_audio=True,
    )
