from __future__ import annotations

import json

import numpy as np
import soundfile as sf
from PIL import Image

from dau.models import IMAGE_MODEL, REFERENCE_MODEL, SPEECH_MODEL
from dau.realtime_audio import _usable_incomplete_audio
from scripts import build_scene_assets, gen_echo_audio


def test_echo_lexical_validation_treats_asr_digits_as_spoken_number_words() -> None:
    numeric = gen_echo_audio._lexical_tokens("Tôi sẽ đến lúc 7 giờ.")
    spoken = gen_echo_audio._lexical_tokens("Tôi sẽ đến lúc bảy giờ.")
    assert numeric == spoken
    assert gen_echo_audio._lexical_tokens("Mã cửa là 236.") == gen_echo_audio._lexical_tokens(
        "Mã cửa là hai ba sáu."
    )


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


def test_scene_asset_receipt_uses_central_image_model(monkeypatch, tmp_path) -> None:
    source_root = tmp_path / "source"
    output_root = tmp_path / "output"
    prompts_path = tmp_path / "prompts.jsonl"
    source_root.mkdir()
    prompts = []
    for index, asset_id in build_scene_assets.ASSETS:
        Image.new("RGB", (160, 90), "#0e0d0c").save(
            source_root / f"{index:03d}-{asset_id}.png"
        )
        prompts.append(
            json.dumps(
                {"size": "1536x1024", "quality": "medium", "prompt": f"Scene {asset_id}"}
            )
        )
    prompts_path.write_text("\n".join(prompts) + "\n", encoding="utf-8")
    monkeypatch.setattr(build_scene_assets, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(build_scene_assets, "PROMPTS_PATH", prompts_path)

    entries = build_scene_assets.build(source_root)
    manifest = json.loads((output_root / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["model"] == IMAGE_MODEL
    assert {entry["model"] for entry in entries} == {IMAGE_MODEL}
