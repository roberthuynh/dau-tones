"""Turn the pure DSP result into the public teaching verdict."""

from __future__ import annotations

import importlib
import json
from functools import lru_cache
from threading import Event, Lock
from time import perf_counter
from typing import Any

import numpy as np

from .content import (
    generic_contour,
    inventory_document,
    target_for,
    validated_targets,
    word_by_id,
    word_surface,
)
from .settings import DATA_ROOT
from .tones import (
    SAMPLE_RATE,
    Accent,
    PitchContour,
    ScoringMode,
    SignalQualityError,
    ToneTemplate,
    canonical_accent,
    canonical_tone,
    classify_contour,
    contour_from_points,
    decode_audio,
    extract_pitch_contour,
    extract_pitch_contour_fast,
    feature_differences,
    tips_from_differences,
    tone_family,
)

_ANALYSIS_RUNTIME_READY = Event()
_ANALYSIS_RUNTIME_LOCK = Lock()
TONE_MARK_LABELS = {
    "ngang": "không dấu",
    "huyen": "dấu huyền",
    "sac": "dấu sắc",
    "hoi": "dấu hỏi",
    "nga": "dấu ngã",
    "nang": "dấu nặng",
}


def _record_timing(timing: dict[str, float] | None, name: str, started: float) -> None:
    if timing is not None:
        timing[name] = (perf_counter() - started) * 1_000.0


def analysis_runtime_ready() -> bool:
    """Return whether this process has initialized librosa and pYIN."""

    return _ANALYSIS_RUNTIME_READY.is_set()


def _extract_audio(
    audio: bytes,
    timing: dict[str, float] | None = None,
) -> PitchContour:
    started = perf_counter()
    samples, sample_rate = decode_audio(audio)
    _record_timing(timing, "decode", started)
    started = perf_counter()
    learner = extract_pitch_contour(samples, sample_rate)
    _record_timing(timing, "pitch", started)
    return learner


def _extract_with_runtime_guard(
    audio: bytes,
    timing: dict[str, float] | None = None,
) -> PitchContour:
    """Analyze once while preventing concurrent pYIN cold compilations."""

    if _ANALYSIS_RUNTIME_READY.is_set():
        return _extract_audio(audio, timing)

    # Never make a learner wait for another instance's pYIN JIT compilation.
    # The page warms pYIN in the background; a newly scaled instance answers
    # immediately with deterministic YIN and the same downstream classifier.
    started = perf_counter()
    samples, sample_rate = decode_audio(audio)
    _record_timing(timing, "decode", started)
    started = perf_counter()
    learner = extract_pitch_contour_fast(samples, sample_rate)
    _record_timing(timing, "pitch_fast", started)
    return learner


def warm_analysis_runtime(timing: dict[str, float] | None = None) -> bool:
    """Initialize the exact production pYIN path before the learner records.

    The endpoint that calls this function is intentionally idempotent. A direct
    analysis arriving at the same time shares the lock, so the expensive first
    import/Numba compilation is never duplicated.
    """

    if _ANALYSIS_RUNTIME_READY.is_set():
        if timing is not None:
            timing["runtime_wait"] = 0.0
        return False

    wait_started = perf_counter()
    with _ANALYSIS_RUNTIME_LOCK:
        _record_timing(timing, "runtime_wait", wait_started)
        if _ANALYSIS_RUNTIME_READY.is_set():
            return False
        sample_count = round(SAMPLE_RATE * 0.48)
        axis = np.arange(sample_count, dtype=np.float64) / SAMPLE_RATE
        envelope = np.sin(np.linspace(0.0, np.pi, sample_count, dtype=np.float64)) ** 2
        waveform = (0.16 * envelope * np.sin(2.0 * np.pi * 180.0 * axis)).astype(np.float32)
        started = perf_counter()
        extract_pitch_contour(waveform, SAMPLE_RATE)
        _record_timing(timing, "pitch_warmup", started)
        started = perf_counter()
        importlib.import_module("av")
        _record_timing(timing, "decoder_warmup", started)
        started = perf_counter()
        templates_for("north")
        templates_for("south")
        _record_timing(timing, "templates_warmup", started)
        _ANALYSIS_RUNTIME_READY.set()
        return True


@lru_cache(maxsize=2)
def scoring_mode(accent: str) -> ScoringMode:
    if accent == "south":
        return ScoringMode.FOUR_FAMILY
    evaluation_path = DATA_ROOT / "evaluation.json"
    if evaluation_path.exists():
        evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    else:
        evaluation = {}
    configured = evaluation.get("accents", {}).get("north", {}).get("scoring_mode")
    return (
        ScoringMode.SIX_TONE if configured in {"six_tone", "six-tone"} else ScoringMode.FOUR_FAMILY
    )


@lru_cache(maxsize=2)
def classifier_profile(accent: str) -> dict[str, Any]:
    """Return the committed browser/server classifier receipt for one accent."""

    path = DATA_ROOT / "classifier_profile.json"
    document = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    profile = document.get("profiles", {}).get(accent, {})
    return {
        "version": str(profile.get("version", "dau-server-dsp-1.0.0")),
        "manifest_hash": str(
            profile.get("manifest_hash", document.get("source_hash", "unversioned"))
        ),
        "temperature": float(profile.get("temperature", 0.32)),
        "abstention_threshold": float(profile.get("abstention_threshold", 0.43)),
    }


@lru_cache(maxsize=2)
def templates_for(accent: str) -> tuple[ToneTemplate, ...]:
    resolved = canonical_accent(accent)
    templates: list[ToneTemplate] = []
    words = {word["id"]: word for word in inventory_document().get("words", [])}
    for target in validated_targets():
        if target.get("accent") != resolved.value or len(target.get("contour", [])) != 64:
            continue
        word = words.get(target.get("word_id"), {})
        templates.append(
            ToneTemplate.from_mapping(
                {
                    "id": f"{resolved.value}:{target.get('word_id')}",
                    "word": word_surface(word) if word else target.get("surface", ""),
                    "tone": target["tone"],
                    "accent": resolved.value,
                    "contour": target["contour"],
                    "features": target.get("features", {}),
                    "path": target.get("path"),
                }
            )
        )
    if templates:
        return tuple(templates)

    # This keeps development and API schema tests operational before Stage 0.
    # Production health reports that these broad priors are not validated.
    for word in inventory_document().get("words", []):
        contour = contour_from_points(generic_contour(word["tone"], resolved.value))
        templates.append(
            ToneTemplate(
                id=f"prior:{resolved.value}:{word['id']}",
                word=word_surface(word),
                tone=canonical_tone(word["tone"]),
                accent=Accent(resolved.value),
                contour=contour.points,
                features=contour.features,
            )
        )
    return tuple(templates)


def _detected_word(intended: dict[str, Any], tone: str) -> dict[str, Any] | None:
    form = _tone_form(intended, tone)
    if form.get("word_id"):
        return word_by_id(str(form["word_id"]))
    for candidate_id in intended.get("minimal_pair_ids", []):
        candidate = word_by_id(candidate_id)
        if candidate and candidate.get("tone") == tone:
            return candidate
    if intended.get("tone") == tone:
        return intended
    return None


def _tone_form(intended: dict[str, Any], tone: str) -> dict[str, Any]:
    """Resolve an orthographic form even when that form has no curated meaning."""

    ascii_base = str(intended.get("ascii_base", ""))
    group = next(
        (
            item
            for item in inventory_document().get("minimal_pair_groups", [])
            if item.get("ascii_base") == ascii_base
        ),
        None,
    )
    form = next(
        (item for item in (group or {}).get("forms", []) if item.get("tone") == tone),
        None,
    )
    if form:
        return dict(form)
    return {
        "tone": tone,
        "surface": word_surface(intended),
        "word_id": intended["id"] if intended.get("tone") == tone else None,
        "meaning_en": intended.get("meaning_en") if intended.get("tone") == tone else None,
    }


def _semantic_status(
    *,
    mode: ScoringMode,
    needs_retry: bool,
    exact_match: bool,
    family_match: bool,
    detected_word: dict[str, Any] | None,
) -> str:
    if needs_retry:
        return "uncertain"
    if mode is ScoringMode.SIX_TONE and exact_match:
        return "exact_correct"
    if mode is ScoringMode.FOUR_FAMILY and family_match and exact_match:
        return "family_correct"
    if mode is ScoringMode.FOUR_FAMILY and family_match:
        return "family_ambiguous"
    return "wrong_known_word" if detected_word else "wrong_no_known_word"


def _meaning_verdict(
    *,
    status: str,
    mode: ScoringMode,
    detected_tone: str,
    intended: dict[str, Any],
    detected_word: dict[str, Any] | None,
) -> dict[str, Any]:
    if status == "uncertain":
        return {
            "status": status,
            "assertion_level": "none",
            "detected_surface": None,
            "detected_meaning_en": None,
            "detected_word_id": None,
            "tone_mark_label": TONE_MARK_LABELS[detected_tone],
        }
    form = _tone_form(intended, detected_tone)
    asserted = (
        intended
        if status in {"exact_correct", "family_correct"}
        else detected_word
        if status == "wrong_known_word"
        else None
    )
    return {
        "status": status,
        "assertion_level": "exact" if mode is ScoringMode.SIX_TONE else "family",
        "detected_surface": word_surface(asserted) if asserted else form.get("surface"),
        "detected_meaning_en": asserted.get("meaning_en") if asserted else None,
        "detected_word_id": asserted.get("id") if asserted else None,
        "tone_mark_label": TONE_MARK_LABELS[detected_tone],
    }


def _signal_confidence(quality: Any) -> float:
    """Keep signal quality separate from classifier probability."""

    voiced = float(quality.voiced_fraction)
    duration = min(1.0, float(quality.active_duration_s) / 0.65)
    rms = min(1.0, float(quality.rms) / 0.08)
    unclipped = 1.0 - min(1.0, float(quality.clipping_fraction) * 50.0)
    return round(
        min(0.99, max(0.0, 0.4 * voiced + 0.25 * duration + 0.2 * rms + 0.15 * unclipped)), 6
    )


def _verdict_copy(intended: dict[str, Any], detected: dict[str, Any] | None) -> str | None:
    if not detected or detected["id"] == intended["id"]:
        return None
    document = inventory_document()
    override = next(
        (
            item
            for item in document.get("verdict_overrides", [])
            if item.get("intended_word_id") == intended["id"]
            and item.get("detected_word_id") == detected["id"]
        ),
        None,
    )
    if override:
        return str(override["copy"])
    return (
        f"You meant {word_surface(intended)}, {intended['meaning_en']}. "
        f"You said {word_surface(detected)}, {detected['meaning_en']}."
    )


def analyze_recording(
    audio: bytes,
    *,
    word_id: str,
    intended_tone: str,
    accent: str,
    timing: dict[str, float] | None = None,
) -> dict[str, Any]:
    total_started = perf_counter()
    try:
        intended = word_by_id(word_id)
        if intended is None:
            raise ValueError(f"Unknown practice word: {word_id}")
        if intended_tone != intended["tone"]:
            raise ValueError("intended_tone does not match the committed inventory word")
        resolved_accent = canonical_accent(accent)
        mode = scoring_mode(resolved_accent.value)
        profile = classifier_profile(resolved_accent.value)
        learner = _extract_with_runtime_guard(audio, timing)
        signal_confidence = _signal_confidence(learner.quality)
        started = perf_counter()
        templates = templates_for(resolved_accent.value)
        _record_timing(timing, "templates", started)
        started = perf_counter()
        result = classify_contour(
            learner,
            templates,
            accent=resolved_accent,
            scoring_mode=mode,
            temperature=profile["temperature"],
            abstention_threshold=profile["abstention_threshold"],
        )
        _record_timing(timing, "classify", started)
        target_entry = target_for(word_id, resolved_accent.value)
        target_contour = (target_entry or {}).get("contour") or generic_contour(
            intended["tone"], resolved_accent.value
        )
        target = contour_from_points(target_contour)
        numeric_diff = feature_differences(learner.features, target.features)
        codes = tips_from_differences(numeric_diff)
        exact_match = result.tone.value == intended["tone"]
        family_match = result.family is tone_family(intended["tone"], resolved_accent)
        needs_retry = result.needs_retry or signal_confidence < 0.35
        detected_candidate = None if needs_retry else _detected_word(intended, result.tone.value)
        semantic_status = _semantic_status(
            mode=mode,
            needs_retry=needs_retry,
            exact_match=exact_match,
            family_match=family_match,
            detected_word=detected_candidate,
        )
        correct = semantic_status in {"exact_correct", "family_correct"}
        meaning_verdict = _meaning_verdict(
            status=semantic_status,
            mode=mode,
            detected_tone=result.tone.value,
            intended=intended,
            detected_word=detected_candidate,
        )
        asserted_word = (
            word_by_id(str(meaning_verdict["detected_word_id"]))
            if meaning_verdict.get("detected_word_id")
            else None
        )
        detected_target = (
            target_for(detected_candidate["id"], resolved_accent.value)
            if detected_candidate is not None
            else None
        )
        detected_contour = (
            None
            if correct or needs_retry
            else (
                (detected_target or {}).get("contour")
                or generic_contour(result.tone.value, resolved_accent.value)
            )
        )
        verification_level = (
            "uncertain" if needs_retry else ("exact" if mode is ScoringMode.SIX_TONE else "family")
        )
        verdict_copy = None
        if semantic_status == "wrong_known_word" and detected_candidate:
            verdict_copy = _verdict_copy(intended, detected_candidate)
        elif semantic_status == "wrong_no_known_word":
            verdict_copy = (
                f"Dấu heard {TONE_MARK_LABELS[result.tone.value]} on "
                f"“{word_surface(intended)}.” That form has no curated meaning in this lesson."
            )
        elif semantic_status == "family_ambiguous":
            verdict_copy = (
                f"The {result.family.value} family matched; the closest exact shape was "
                f"{TONE_MARK_LABELS[result.tone.value]}."
            )
        return {
            "tone_detected": result.tone.value,
            "tone_intended": intended["tone"],
            "intended_word_id": intended["id"],
            "detected_word_id": meaning_verdict["detected_word_id"],
            "correct": correct,
            "confidence": result.confidence,
            "learner_contour": learner.as_dict()["contour"],
            "target_contour": [round(float(value), 5) for value in target.points],
            "detected_contour": (
                [round(float(value), 5) for value in detected_contour]
                if detected_contour is not None
                else None
            ),
            "tips_features": {"codes": codes, "numeric": numeric_diff},
            "grading_mode": "six_tone" if mode is ScoringMode.SIX_TONE else "four_family",
            "exact_verified": mode is ScoringMode.SIX_TONE and not needs_retry,
            "family_verified": not needs_retry,
            "tone_family": result.family.value,
            "intended_family": tone_family(intended["tone"], resolved_accent).value,
            "exact_tone_match": exact_match,
            "family_correct": family_match,
            "verification_level": verification_level,
            "alternatives": [
                {
                    "tone": item.tone.value,
                    "family": item.family.value,
                    "score": round(item.score, 6),
                    "confidence": round(item.probability, 6),
                }
                for item in result.alternatives
            ],
            "tone_alternatives": [item.as_dict() for item in result.alternatives],
            "needs_retry": needs_retry,
            "signal_quality": learner.as_dict()["quality"],
            "word": word_id,
            "intended_word": {
                "id": intended["id"],
                "surface": word_surface(intended),
                "meaning_en": intended["meaning_en"],
                "art_url": f"/art/{intended['id']}.png",
            },
            "detected_word": (
                {
                    "id": asserted_word["id"],
                    "surface": word_surface(asserted_word),
                    "meaning_en": asserted_word["meaning_en"],
                    "art_url": f"/art/{asserted_word['id']}.png",
                }
                if asserted_word
                else None
            ),
            "verdict_copy": verdict_copy,
            "target_validated": bool(target_entry),
            "semantic_status": semantic_status,
            "class_confidence": result.confidence,
            "signal_confidence": signal_confidence,
            "meaning_verdict": meaning_verdict,
            "classifier_version": profile["version"],
            "classifier_manifest_hash": profile["manifest_hash"],
        }
    finally:
        _record_timing(timing, "total", total_started)


__all__ = [
    "SignalQualityError",
    "analysis_runtime_ready",
    "analyze_recording",
    "classifier_profile",
    "scoring_mode",
    "templates_for",
    "warm_analysis_runtime",
]
