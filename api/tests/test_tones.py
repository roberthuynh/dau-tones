from __future__ import annotations

import math

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
    expected_tone_contour,
    feature_differences,
    isolate_primary_speech,
    tips_from_differences,
    tone_family,
    validate_target_candidate,
)


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


@pytest.mark.parametrize("tone", TONE_ORDER)
def test_expected_shape_passes_target_validation(tone: Tone) -> None:
    validation = validate_target_candidate(_fixture_analysis(tone), tone, accent=Accent.NORTH)
    assert validation.passed, validation.reason_codes
    assert validation.shape_score >= 0.0


def test_wrong_expected_tone_fails_target_validation() -> None:
    validation = validate_target_candidate(_fixture_analysis(Tone.SAC), Tone.HUYEN)
    assert not validation.passed
    assert "wrong_tone_shape" in validation.reason_codes or "no_fall" in validation.reason_codes


def test_feature_diff_produces_physical_tip_codes() -> None:
    learner = _fixture_analysis(Tone.NGANG).features
    target = _fixture_analysis(Tone.SAC).features
    differences = feature_differences(learner, target)
    tips = tips_from_differences(differences)
    assert "no_final_rise" in tips or "range_too_flat" in tips
