from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

import eval as evaluation
from dau.tones import (
    Accent,
    ScoringMode,
    Tone,
    ToneTemplate,
    contour_from_points,
    expected_tone_contour,
)


def _template(
    target_id: str,
    word: str,
    tone: Tone,
    accent: Accent = Accent.NORTH,
) -> ToneTemplate:
    analysis = contour_from_points(expected_tone_contour(tone, accent))
    return ToneTemplate(
        id=target_id,
        word=word,
        tone=tone,
        accent=accent,
        contour=analysis.points,
        features=analysis.features,
    )


def _prediction(
    target_id: str,
    actual: str,
    predicted: str,
    *,
    needs_retry: bool = False,
) -> evaluation.FoldPrediction:
    return evaluation.FoldPrediction(
        target_id=target_id,
        word=target_id,
        accent="north",
        actual_tone=actual,
        predicted_tone=predicted,
        actual_label=actual,
        predicted_label=predicted,
        confidence=0.8,
        needs_retry=needs_retry,
        temperature=0.32,
        abstention_threshold=0.43,
    )


def test_fold_training_excludes_unicode_equivalent_word_and_other_accent() -> None:
    held_out = _template("held", "mã", Tone.NGA)
    decomposed_same_word = _template(
        "same-word-second-take",
        unicodedata.normalize("NFD", "MÃ"),
        Tone.NGA,
    )
    other_northern_word = _template("other-word", "ngã", Tone.NGA)
    southern_word = _template("south", "ngã", Tone.NGA, Accent.SOUTH)

    training = evaluation._fold_training_set(
        [held_out, decomposed_same_word, other_northern_word, southern_word],
        held_out,
        Accent.NORTH,
    )

    assert [template.id for template in training] == ["other-word"]


def test_grouped_outer_fold_records_calibrated_abstention(monkeypatch: pytest.MonkeyPatch) -> None:
    templates = [
        _template("first", "mã", Tone.NGA),
        _template("second", "ngã", Tone.NGA),
    ]
    monkeypatch.setattr(
        evaluation,
        "_calibrate_fold",
        lambda *_args, **_kwargs: (0.20, 0.99),
    )

    predictions = evaluation.grouped_leave_one_word_out(
        templates,
        Accent.NORTH,
        ScoringMode.SIX_TONE,
    )

    assert len(predictions) == 2
    assert all(prediction.needs_retry for prediction in predictions)
    assert {prediction.temperature for prediction in predictions} == {0.20}
    assert {prediction.abstention_threshold for prediction in predictions} == {0.99}


def test_calibration_uses_deterministic_defaults_without_inner_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(evaluation, "_inner_scores", lambda *_args, **_kwargs: [])

    calibrated = evaluation._calibrate_fold([], Accent.NORTH, ScoringMode.SIX_TONE)

    assert calibrated == (0.32, 0.43)


def test_calibration_prefers_sharp_confidence_for_consistently_correct_inner_folds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation,
        "_inner_scores",
        lambda *_args, **_kwargs: [
            (True, [0.0, 1.5, 2.0, 2.5]),
            (True, [0.1, 1.4, 2.1, 2.8]),
            (True, [0.0, 1.8, 2.2, 2.7]),
        ],
    )

    temperature, threshold = evaluation._calibrate_fold(
        [], Accent.NORTH, ScoringMode.SIX_TONE
    )

    assert temperature == 0.20
    assert threshold == 0.30


def test_confusion_matrix_and_metrics_exclude_abstentions_by_default() -> None:
    predictions = [
        _prediction("correct", "ngang", "ngang"),
        _prediction("wrong", "ngang", "sac"),
        _prediction("retry", "sac", "sac", needs_retry=True),
    ]
    labels = ["ngang", "sac"]

    covered_matrix = evaluation.confusion_matrix(predictions, labels)
    all_matrix = evaluation.confusion_matrix(predictions, labels, include_abstentions=True)
    metrics = evaluation._metrics(predictions, labels)

    assert covered_matrix == [[1, 1], [0, 0]]
    assert all_matrix == [[1, 1], [0, 1]]
    assert metrics["samples"] == 3
    assert metrics["covered"] == 2
    assert metrics["coverage"] == pytest.approx(2 / 3, abs=1e-6)
    assert metrics["accuracy"] == 0.5


def test_manifest_audio_is_hash_checked_and_reanalyzed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "target.wav"
    audio_path.write_bytes(b"fixture audio bytes")
    analysis = contour_from_points(expected_tone_contour(Tone.SAC))
    calls: list[Path] = []

    def analyze(path: Path):
        calls.append(path)
        return analysis

    monkeypatch.setattr(evaluation, "analyze_audio", analyze)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "word_id": "ma-mother",
                        "word": "má",
                        "tone": "sac",
                        "accent": "north",
                        "path": audio_path.name,
                        "sha256": hashlib.sha256(audio_path.read_bytes()).hexdigest(),
                        "contour": [0.0] * 64,
                        "features": {"slope": 0.0},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    templates = evaluation.load_templates(manifest_path)

    assert calls == [audio_path]
    assert templates[0].contour == pytest.approx(analysis.points)


def test_manifest_audio_hash_mismatch_stops_evaluation(tmp_path: Path) -> None:
    audio_path = tmp_path / "target.wav"
    audio_path.write_bytes(b"fixture audio bytes")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "word_id": "ma-mother",
                        "word": "má",
                        "tone": "sac",
                        "accent": "north",
                        "path": audio_path.name,
                        "sha256": "0" * 64,
                        "contour": [0.0] * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        evaluation.load_templates(manifest_path)
