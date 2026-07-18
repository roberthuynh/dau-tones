from __future__ import annotations

from typing import Any

import pytest

from dau import analysis_service
from dau.content import generic_contour, word_by_id
from dau.schemas import AnalysisResponse
from dau.tones import (
    ClassificationResult,
    ScoringMode,
    Tone,
    ToneAlternative,
    ToneFamily,
    contour_from_points,
)


def _classification(tone: Tone, family: ToneFamily) -> ClassificationResult:
    return ClassificationResult(
        tone=tone,
        family=family,
        confidence=0.84,
        scoring_mode=ScoringMode.SIX_TONE,
        exact_verified=True,
        needs_retry=False,
        alternatives=(
            ToneAlternative(tone=tone, family=family, score=0.12, probability=0.84),
            ToneAlternative(
                tone=Tone.HUYEN,
                family=ToneFamily.FALLING,
                score=0.44,
                probability=0.10,
            ),
            ToneAlternative(
                tone=Tone.NGANG,
                family=ToneFamily.LEVEL,
                score=0.57,
                probability=0.06,
            ),
        ),
        scores={tone.value: 0.12},
    )


def _analyze_with_result(
    monkeypatch: pytest.MonkeyPatch,
    *,
    word_id: str,
    mode: ScoringMode,
    tone: Tone,
    family: ToneFamily,
) -> dict[str, Any]:
    word = word_by_id(word_id)
    assert word is not None
    learner = contour_from_points(generic_contour(tone.value, "north"))
    result = _classification(tone, family)
    monkeypatch.setattr(analysis_service, "scoring_mode", lambda _accent: mode)
    monkeypatch.setattr(
        analysis_service, "_extract_with_runtime_guard", lambda _audio, _timing: learner
    )
    monkeypatch.setattr(analysis_service, "templates_for", lambda _accent: ())
    monkeypatch.setattr(analysis_service, "classify_contour", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(analysis_service, "target_for", lambda *_args, **_kwargs: None)
    return analysis_service.analyze_recording(
        b"fixture",
        word_id=word_id,
        intended_tone=word["tone"],
        accent="north",
    )


def test_six_tone_no_meaning_verdict_never_invents_a_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _analyze_with_result(
        monkeypatch,
        word_id="phuong-name",
        mode=ScoringMode.SIX_TONE,
        tone=Tone.NGA,
        family=ToneFamily.RISING,
    )
    validated = AnalysisResponse.model_validate(payload)
    assert validated.semantic_status == "wrong_no_known_word"
    assert validated.correct is False
    assert validated.detected_word_id is None
    assert validated.detected_word is None
    assert validated.meaning_verdict.detected_surface == "phưỡng"
    assert validated.meaning_verdict.detected_meaning_en is None
    assert validated.meaning_verdict.assertion_level == "exact"
    assert validated.verdict_copy == (
        "Dấu heard dấu ngã on “Phương.” That form has no curated meaning in this lesson."
    )
    assert validated.class_confidence == validated.confidence == 0.84
    assert validated.signal_confidence > 0.9
    assert validated.classifier_version.startswith("dau-")
    assert len(validated.classifier_manifest_hash) == 64


def test_four_family_ambiguity_withholds_exact_phoenix_meaning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _analyze_with_result(
        monkeypatch,
        word_id="phuong-ward",
        mode=ScoringMode.FOUR_FAMILY,
        tone=Tone.NANG,
        family=ToneFamily.FALLING,
    )
    validated = AnalysisResponse.model_validate(payload)
    assert validated.semantic_status == "family_ambiguous"
    assert validated.correct is False
    assert validated.family_correct is True
    assert validated.exact_tone_match is False
    assert validated.meaning_verdict.assertion_level == "family"
    assert validated.meaning_verdict.detected_surface == "phượng"
    assert validated.meaning_verdict.detected_meaning_en is None
    assert validated.meaning_verdict.detected_word_id is None
    assert validated.detected_word is None
    assert validated.verdict_copy == (
        "The falling family matched; the closest exact shape was dấu nặng."
    )


def test_six_tone_known_word_verdict_can_assert_phoenix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _analyze_with_result(
        monkeypatch,
        word_id="phuong-name",
        mode=ScoringMode.SIX_TONE,
        tone=Tone.NANG,
        family=ToneFamily.FALLING,
    )
    validated = AnalysisResponse.model_validate(payload)
    assert validated.semantic_status == "wrong_known_word"
    assert validated.meaning_verdict.assertion_level == "exact"
    assert validated.detected_word_id == "phuong-phoenix"
    assert validated.meaning_verdict.detected_meaning_en == "phoenix"
    assert validated.detected_word is not None
    assert validated.detected_word.surface == "phượng"
    assert "phoenix" in (validated.verdict_copy or "")
