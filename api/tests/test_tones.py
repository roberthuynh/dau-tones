from __future__ import annotations

import io
import math
import wave

import numpy as np
import pytest

from dau.tones import (
    TONE_ORDER,
    Accent,
    ScoringMode,
    SignalQualityCode,
    SignalQualityError,
    Tone,
    ToneFamily,
    ToneTemplate,
    classify_contour,
    constrained_dtw_distance,
    contour_from_points,
    decode_audio,
    expected_tone_contour,
    extract_pitch_contour,
    feature_differences,
    isolate_primary_speech,
    tips_from_differences,
    tone_family,
    validate_target_candidate,
)


def _wav(samples: np.ndarray, sample_rate: int = 22_050) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
    return output.getvalue()


def _fixture_analysis(tone: Tone, accent: Accent = Accent.NORTH):
    return contour_from_points(
        expected_tone_contour(tone, accent),
        duration_s=0.30 if tone is Tone.NANG else 0.55,
        central_rms_dip=0.50 if tone is Tone.NGA else 0.0,
        terminal_energy_drop=0.50 if tone is Tone.NANG else 0.0,
    )


def _templates(accent: Accent = Accent.NORTH) -> list[ToneTemplate]:
    result = []
    for index, tone in enumerate(TONE_ORDER):
        analysis = _fixture_analysis(tone, accent)
        result.append(
            ToneTemplate(
                id=f"{accent.value}-{tone.value}",
                word=f"word-{index}",
                tone=tone,
                accent=accent,
                contour=analysis.points,
                features=analysis.features,
            )
        )
    return result


@pytest.mark.parametrize("tone", TONE_ORDER)
def test_six_synthetic_tone_shapes_classify(tone: Tone) -> None:
    result = classify_contour(
        _fixture_analysis(tone),
        _templates(),
        accent=Accent.NORTH,
        scoring_mode=ScoringMode.SIX_TONE,
        abstention_threshold=0.0,
    )
    assert result.tone is tone
    assert not result.needs_retry
    assert 0.0 <= result.confidence <= 0.95


def test_constrained_dtw_tolerates_small_time_warp() -> None:
    contour = expected_tone_contour(Tone.HOI)
    source_axis = np.linspace(0.0, 1.0, contour.size)
    warped_axis = np.clip(source_axis**1.08, 0.0, 1.0)
    warped = np.interp(warped_axis, source_axis, contour)
    same_distance = constrained_dtw_distance(contour, contour)
    warped_distance = constrained_dtw_distance(contour, warped)
    wrong_distance = constrained_dtw_distance(contour, expected_tone_contour(Tone.SAC))
    assert same_distance == pytest.approx(0.0)
    assert warped_distance < wrong_distance


def test_southern_hoi_and_nga_share_dipping_family() -> None:
    assert tone_family(Tone.HOI, Accent.SOUTH) is ToneFamily.DIPPING
    assert tone_family(Tone.NGA, Accent.SOUTH) is ToneFamily.DIPPING
    assert tone_family(Tone.NGA, Accent.NORTH) is ToneFamily.RISING


def test_four_family_result_is_honest_about_exact_verification() -> None:
    result = classify_contour(
        _fixture_analysis(Tone.NGA, Accent.SOUTH),
        _templates(Accent.SOUTH),
        accent=Accent.SOUTH,
        scoring_mode=ScoringMode.FOUR_FAMILY,
        abstention_threshold=0.0,
    )
    assert result.family is ToneFamily.DIPPING
    assert not result.exact_verified


def test_high_abstention_threshold_requests_retry() -> None:
    result = classify_contour(
        _fixture_analysis(Tone.NGANG),
        _templates(),
        abstention_threshold=0.99,
    )
    assert result.needs_retry
    assert result.confidence <= 0.95


def test_silence_is_a_typed_quality_error() -> None:
    with pytest.raises(SignalQualityError) as captured:
        isolate_primary_speech(np.zeros(22_050), 22_050)
    assert captured.value.code is SignalQualityCode.SILENCE
    assert captured.value.as_dict()["code"] == "silence"


def test_pcm_wav_uses_standard_decoder_without_importing_pyav(monkeypatch) -> None:
    time = np.arange(4_410) / 22_050
    voice = 0.2 * np.sin(2 * np.pi * 180 * time)
    monkeypatch.setattr(
        "dau.tones._decode_av",
        lambda _source: (_ for _ in ()).throw(AssertionError("PyAV should not decode PCM WAV")),
    )

    samples, sample_rate = decode_audio(_wav(voice))

    assert sample_rate == 22_050
    assert samples.shape == voice.shape
    assert np.max(np.abs(samples)) == pytest.approx(0.2, abs=0.001)


def test_rejected_target_metrics_are_strict_json_values() -> None:
    validation = validate_target_candidate(b"not a wav", Tone.NGANG)

    assert not validation.passed
    assert validation.as_dict()["shape_score"] is None
    assert validation.as_dict()["separation_margin"] is None


def test_clipping_is_a_typed_quality_error() -> None:
    clipped = np.ones(22_050) * 0.999
    with pytest.raises(SignalQualityError) as captured:
        isolate_primary_speech(clipped, 22_050)
    assert captured.value.code is SignalQualityCode.CLIPPED


def test_two_substantial_islands_are_rejected() -> None:
    sample_rate = 22_050
    time = np.arange(round(0.28 * sample_rate)) / sample_rate
    syllable = 0.15 * np.sin(2.0 * math.pi * 180.0 * time)
    waveform = np.concatenate(
        (np.zeros(2_000), syllable, np.zeros(8_000), syllable, np.zeros(2_000))
    )
    with pytest.raises(SignalQualityError) as captured:
        isolate_primary_speech(waveform, sample_rate)
    assert captured.value.code is SignalQualityCode.MULTIPLE_UTTERANCES


def test_pyin_decoded_voicing_is_used_when_frame_probabilities_are_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sample_rate = 22_050
    time = np.arange(round(0.42 * sample_rate)) / sample_rate
    syllable = 0.15 * np.sin(2.0 * math.pi * 180.0 * time)
    waveform = np.concatenate((np.zeros(1_500), syllable, np.zeros(1_500)))

    def low_probability_track(*_args, **_kwargs):
        frame_count = 36
        return (
            np.full(frame_count, 180.0),
            np.ones(frame_count, dtype=bool),
            np.full(frame_count, 0.12),
        )

    monkeypatch.setattr("librosa.pyin", low_probability_track)

    analysis = extract_pitch_contour(waveform, sample_rate)

    assert analysis.quality.voiced_fraction == pytest.approx(1.0)
    assert np.all(analysis.raw_voiced)
    assert np.max(np.abs(analysis.points)) < 1e-8


def test_librosa_stub_fallback_uses_vendored_package_data(monkeypatch) -> None:
    from dau import librosa_compat

    original = librosa_compat._ORIGINAL_ATTACH_STUB

    def missing_then_real(package_name: str, filename: str):
        if filename == "/stripped/librosa/__init__.py":
            raise ValueError(
                "Cannot load imports from non-existent stub '/stripped/librosa/__init__.pyi'"
            )
        return original(package_name, filename)

    monkeypatch.setattr(librosa_compat, "_ORIGINAL_ATTACH_STUB", missing_then_real)

    _getattr, _dir, exported = librosa_compat._attach_stub_with_fallback(
        "librosa", "/stripped/librosa/__init__.py"
    )

    assert "pyin" in exported
    assert "resample" in exported


@pytest.mark.parametrize("tone", TONE_ORDER)
def test_expected_shape_passes_target_validation(tone: Tone) -> None:
    validation = validate_target_candidate(_fixture_analysis(tone), tone, accent=Accent.NORTH)
    assert validation.passed, validation.reason_codes
    assert validation.shape_score >= 0.0


def test_wrong_expected_tone_fails_target_validation() -> None:
    validation = validate_target_candidate(_fixture_analysis(Tone.SAC), Tone.HUYEN)
    assert not validation.passed
    assert "wrong_tone_shape" in validation.reason_codes or "no_fall" in validation.reason_codes


def test_target_validation_adapts_to_a_wider_correct_pitch_excursion() -> None:
    emphatic_rise = contour_from_points(
        expected_tone_contour(Tone.SAC) * 3.5,
        duration_s=0.4,
    )

    validation = validate_target_candidate(emphatic_rise, Tone.SAC)

    assert validation.passed, validation.reason_codes
    assert validation.shape_score <= 1.15
    assert validation.separation_margin >= -0.08


def test_southern_dipping_family_uses_pitch_and_energy_evidence() -> None:
    x = np.linspace(0.0, 1.0, 64)
    asymmetric_dip = np.where(x < 0.45, 1.0 - 4.5 * x, -1.025 + 9.0 * (x - 0.45) / 0.55)
    analysis = contour_from_points(
        asymmetric_dip,
        duration_s=0.45,
        central_rms_dip=0.4,
    )

    validation = validate_target_candidate(
        analysis,
        Tone.NGA,
        accent=Accent.SOUTH,
    )

    assert validation.passed, validation.reason_codes
    assert validation.accent_family_verified


def test_feature_diff_produces_physical_tip_codes() -> None:
    learner = _fixture_analysis(Tone.NGANG).features
    target = _fixture_analysis(Tone.SAC).features
    differences = feature_differences(learner, target)
    tips = tips_from_differences(differences)
    assert "no_final_rise" in tips or "range_too_flat" in tips
