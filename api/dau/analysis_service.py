"""Turn the pure DSP result into the public teaching verdict."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

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
    Accent,
    ScoringMode,
    SignalQualityError,
    ToneTemplate,
    analyze_audio,
    canonical_accent,
    canonical_tone,
    classify_contour,
    contour_from_points,
    feature_differences,
    tips_from_differences,
    tone_family,
)


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
    for candidate_id in intended.get("minimal_pair_ids", []):
        candidate = word_by_id(candidate_id)
        if candidate and candidate.get("tone") == tone:
            return candidate
    if intended.get("tone") == tone:
        return intended
    return None


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
        return override["copy"]
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
) -> dict[str, Any]:
    intended = word_by_id(word_id)
    if intended is None:
        raise ValueError(f"Unknown practice word: {word_id}")
    if intended_tone != intended["tone"]:
        raise ValueError("intended_tone does not match the committed inventory word")
    resolved_accent = canonical_accent(accent)
    mode = scoring_mode(resolved_accent.value)
    learner = analyze_audio(audio)
    result = classify_contour(
        learner,
        templates_for(resolved_accent.value),
        accent=resolved_accent,
        scoring_mode=mode,
    )
    target_entry = target_for(word_id, resolved_accent.value)
    target_contour = (target_entry or {}).get("contour") or generic_contour(
        intended["tone"], resolved_accent.value
    )
    target = contour_from_points(target_contour)
    numeric_diff = feature_differences(learner.features, target.features)
    codes = tips_from_differences(numeric_diff)
    exact_match = result.tone.value == intended["tone"]
    family_match = result.family is tone_family(intended["tone"], resolved_accent)
    correct = exact_match if mode is ScoringMode.SIX_TONE else family_match
    detected = None if result.needs_retry else _detected_word(intended, result.tone.value)
    detected_target = (
        target_for(detected["id"], resolved_accent.value) if detected is not None else None
    )
    detected_contour = (
        (detected_target or {}).get("contour")
        or (generic_contour(result.tone.value, resolved_accent.value) if detected else None)
    )
    verification_level = (
        "uncertain"
        if result.needs_retry
        else ("exact" if mode is ScoringMode.SIX_TONE else "family")
    )
    return {
        "tone_detected": result.tone.value,
        "tone_intended": intended["tone"],
        "intended_word_id": intended["id"],
        "detected_word_id": detected["id"] if detected else None,
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
        "exact_verified": result.exact_verified and not result.needs_retry,
        "family_verified": not result.needs_retry,
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
        "needs_retry": result.needs_retry,
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
                "id": detected["id"],
                "surface": word_surface(detected),
                "meaning_en": detected["meaning_en"],
                "art_url": f"/art/{detected['id']}.png",
            }
            if detected
            else None
        ),
        "verdict_copy": _verdict_copy(intended, detected),
        "target_validated": bool(target_entry),
    }


__all__ = ["SignalQualityError", "analyze_recording", "scoring_mode", "templates_for"]
