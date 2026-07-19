"""Specific tone coaching with a deterministic offline contract."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .content import inventory_document, word_by_id
from .models import TEXT_MODEL
from .schemas import CoachRequest, CoachResponse, DrillRequest, DrillSelection
from .settings import AI_TIMEOUT_SECONDS, openai_api_key

PHYSICAL_TIPS = {
    "started_too_high": "Start lower, then let the pitch travel into the tone.",
    "started_too_low": "Begin a little higher so the tone has room to move.",
    "ended_too_high": "Let your chin settle sooner so the ending lands lower.",
    "ended_too_low": "Keep the vowel supported and finish a little higher.",
    "no_final_rise": "Keep the vowel open and lift your chin through the final rise.",
    "fell_instead_of_level": "Hold your chin still and carry the pitch straight through the vowel.",
    "too_flat": "Give the vowel more pitch movement instead of holding it in one place.",
    "range_too_flat": "Give the vowel more pitch movement instead of holding it in one place.",
    "dip_too_early": "Delay the dip until the middle of the vowel, then recover smoothly.",
    "dip_too_late": "Let the pitch turn downward earlier, around the middle of the vowel.",
    "missing_dip": "Drop into the middle of the vowel before you bring the pitch back up.",
    "too_long": "Make the syllable shorter and close the sound firmly at the end.",
    "too_short": "Give the vowel a little more time so the full contour can appear.",
    "weak_glottal_break": (
        "Briefly tighten at the throat in the middle, then release into the rise."
    ),
    "needs_retry": "Try once more in a quiet breath, holding the phone about a hand away.",
    "match_the_target_shape": (
        "Trace the target with your chin while keeping the vowel open and steady."
    ),
}


def _openai_client(key: str) -> Any:
    """Import the optional model client only on an AI-backed request."""

    from openai import OpenAI

    return OpenAI(api_key=key, timeout=AI_TIMEOUT_SECONDS, max_retries=0)


def _tip_codes(verdict: dict[str, Any]) -> list[str]:
    raw = verdict.get("tips_features", [])
    if isinstance(raw, dict):
        raw = raw.get("codes", [])
    codes: list[str] = []
    for item in raw if isinstance(raw, list) else []:
        code = item if isinstance(item, str) else item.get("code")
        if code:
            codes.append(str(code))
    if verdict.get("needs_retry"):
        codes.insert(0, "needs_retry")
    return codes[:12]


def _numeric_differences(verdict: dict[str, Any]) -> dict[str, float]:
    tips = verdict.get("tips_features", {})
    raw = tips.get("numeric", {}) if isinstance(tips, dict) else {}
    return dict(
        list(
            {
                str(key): float(value)
                for key, value in raw.items()
                if isinstance(value, int | float) and not isinstance(value, bool)
            }.items()
        )[:16]
    )


def _sanitized_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "intended_tone": item.get("tone_intended") or item.get("intended_tone"),
            "detected_tone": item.get("tone_detected") or item.get("detected_tone"),
            "semantic_status": item.get("semantic_status"),
            "correct": item.get("correct") if isinstance(item.get("correct"), bool) else None,
        }
        for item in history[-12:]
    ]


def _difference(numeric: dict[str, float], *names: str) -> float | None:
    return next((numeric[name] for name in names if name in numeric), None)


def _measured_observation(verdict: dict[str, Any], codes: list[str]) -> str:
    """Turn the first correction code into one factual, learner-facing measurement."""

    numeric = _numeric_differences(verdict)
    code = next((item for item in codes if item != "match_the_target_shape"), None)
    if code == "needs_retry":
        return "The pitch tracker could not recover one stable 64-point contour from this take."
    if code in {"started_too_high", "started_too_low"}:
        value = _difference(numeric, "start", "start_semitones")
        if value is not None:
            direction = "above" if value > 0 else "below"
            return f"Your pitch began {abs(value):.1f} semitones {direction} the target."
    if code in {"ended_too_high", "ended_too_low", "fell_instead_of_level"}:
        value = _difference(numeric, "end", "end_semitones")
        if value is not None:
            direction = "above" if value > 0 else "below"
            return f"Your ending landed {abs(value):.1f} semitones {direction} the target."
    if code == "no_final_rise":
        value = _difference(numeric, "final_rise")
        if value is not None:
            return f"Your final rise was {abs(value):.1f} semitones smaller than the target."
    if code in {"too_flat", "range_too_flat"}:
        value = _difference(numeric, "pitch_range")
        if value is not None:
            comparison = "narrower" if value < 0 else "wider"
            return f"Your pitch range was {abs(value):.1f} semitones {comparison} than the target."
    if code in {"dip_too_early", "dip_too_late", "missing_dip"}:
        value = _difference(numeric, "dip_position")
        if value is not None:
            direction = "later" if value > 0 else "earlier"
            return f"Your lowest point arrived {abs(value) * 100:.0f}% of the vowel {direction}."
    if code in {"too_long", "too_short"}:
        value = _difference(numeric, "duration_s")
        if value is not None:
            comparison = "longer" if value > 0 else "shorter"
            return f"Your vowel was {abs(value) * 1000:.0f} milliseconds {comparison} than target."
    if code == "weak_glottal_break":
        value = _difference(numeric, "central_rms_dip")
        if value is not None:
            return (
                f"Your middle energy dip was {abs(value) * 100:.0f} percentage points too shallow."
            )

    confidence = verdict.get("class_confidence", verdict.get("confidence"))
    if isinstance(confidence, int | float) and not isinstance(confidence, bool):
        label = "target" if verdict.get("correct") else "closest measured shape"
        percent = float(confidence) * 100
        return f"The 64-point contour matched its {label} at {percent:.0f}% confidence."
    return "The pitch tracker recovered a full contour and found a measurable shape difference."


def _next_word(request: CoachRequest) -> tuple[str, str]:
    document = inventory_document()
    featured = document.get("featured_queue", [])
    current = str(request.verdict.get("word") or request.verdict.get("word_id") or "phuong")
    errors: list[str] = []
    for item in request.history[-12:]:
        history_tone = item.get("tone_intended") or item.get("intended_tone")
        if item.get("correct") is False and history_tone:
            errors.append(str(history_tone))
    tone = (
        Counter(errors).most_common(1)[0][0]
        if errors
        else request.verdict.get("tone_intended") or request.verdict.get("intended_tone")
    )
    candidates = [
        word["id"]
        for word in document.get("words", [])
        if word.get("tone") == tone and word.get("id") != current
    ]
    if candidates:
        next_id = candidates[0]
        return next_id, f"because {tone} is the tone that needs the most repetitions"
    if current in featured and len(featured) > 1:
        next_id = featured[(featured.index(current) + 1) % len(featured)]
    else:
        next_id = featured[0] if featured else current
    return next_id, "because contrasting the next contour makes this correction easier to feel"


def deterministic_coach(request: CoachRequest) -> CoachResponse:
    codes = _tip_codes(request.verdict)
    sentence = next((PHYSICAL_TIPS[code] for code in codes if code in PHYSICAL_TIPS), None)
    if not sentence:
        sentence = (
            "Match the gray curve physically: move your chin with the pitch and keep the "
            "vowel steady."
        )
    next_id, rationale = _next_word(request)
    return CoachResponse(
        observation=_measured_observation(request.verdict, codes),
        coaching_sentence=sentence,
        next_word=next_id,
        rationale=rationale,
        source="rules",
    )


def coach(request: CoachRequest, *, safety_identifier: str | None = None) -> CoachResponse:
    fallback = deterministic_coach(request)
    key = openai_api_key()
    if not key:
        return fallback.model_copy(
            update={"refinement_status": "no_key", "fallback_reason": "no_api_key"}
        )
    valid_ids = [word["id"] for word in inventory_document().get("words", [])]
    meaning = request.verdict.get("meaning_verdict", {})
    meaning = meaning if isinstance(meaning, dict) else {}
    confusion_history = [
        {
            "intended_tone": item.get("tone_intended") or item.get("intended_tone"),
            "detected_tone": item.get("tone_detected") or item.get("detected_tone"),
            "semantic_status": item.get("semantic_status"),
            "correct": item.get("correct"),
        }
        for item in request.history[-12:]
        if item.get("correct") is False
    ]
    try:
        client = _openai_client(key)
        arguments: dict[str, Any] = {
            "model": TEXT_MODEL,
            "reasoning": {"effort": "low"},
            "text": {"verbosity": "low"},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "You are an encouraging, precise Vietnamese tone coach for heritage "
                        "learners. Give exactly one concrete physical instruction, never generic "
                        "praise. Observation must state one supplied measurement and must not "
                        "invent a number. Never reclassify the tone or assert an accidental "
                        "meaning beyond the supplied assertion level and known meaning. Select "
                        "the next word only from the supplied IDs and explain the selection in "
                        "one short visible rationale."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "intended_tone": request.verdict.get("tone_intended")
                            or request.verdict.get("intended_tone"),
                            "detected_tone": request.verdict.get("tone_detected")
                            or request.verdict.get("detected_tone"),
                            "semantic_status": request.verdict.get("semantic_status"),
                            "assertion_level": meaning.get("assertion_level", "none"),
                            "known_meaning": meaning.get("detected_meaning_en"),
                            "feature_differences": _numeric_differences(request.verdict),
                            "feature_codes": _tip_codes(request.verdict),
                            "class_confidence": request.verdict.get("class_confidence"),
                            "signal_confidence": request.verdict.get("signal_confidence"),
                            "confusion_pair_history": confusion_history,
                            "accent": request.accent,
                            "valid_word_ids": valid_ids,
                            "offline_suggestion": fallback.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text_format": CoachResponse,
            # GPT-5.6 reasoning tokens share this ceiling with the structured
            # payload. A 180-token cap can complete reasoning with no JSON.
            "max_output_tokens": 600,
            "store": False,
        }
        if safety_identifier:
            arguments["safety_identifier"] = safety_identifier
        response = client.responses.parse(**arguments)
        parsed = response.output_parsed
        if (
            parsed is None
            or parsed.next_word not in valid_ids
            or word_by_id(parsed.next_word) is None
        ):
            return fallback.model_copy(
                update={"refinement_status": "failed", "fallback_reason": "invalid_response"}
            )
        return CoachResponse.model_validate(
            {
                **parsed.model_dump(mode="json"),
                "source": "gpt-5.6-sol",
                "refinement_status": "complete",
                "fallback_reason": None,
            }
        )
    except Exception as error:
        timed_out = "timeout" in type(error).__name__.lower()
        return fallback.model_copy(
            update={
                "refinement_status": "timeout" if timed_out else "failed",
                "fallback_reason": "provider_timeout" if timed_out else "provider_unavailable",
            }
        )


def generate_drill(
    request: DrillRequest, *, safety_identifier: str | None = None
) -> dict[str, Any]:
    document = inventory_document()
    themed = {item["id"]: item.get("word_ids", []) for item in document.get("themed_drills", [])}
    seeded = list(themed.get(request.theme, []))
    valid_ids = {word["id"] for word in document.get("words", [])}
    fallback_ids = [item for item in seeded if item in valid_ids][: request.size]
    if len(fallback_ids) < request.size:
        fallback_ids.extend(
            item for item in document.get("featured_queue", []) if item not in fallback_ids
        )
    fallback = {
        "word_ids": fallback_ids[: request.size],
        "rationale": (
            f"A {request.theme} set that contrasts the shapes you will use in real speech."
        ),
        "source": "rules",
    }
    key = openai_api_key()
    if not key:
        return fallback
    try:
        client = _openai_client(key)
        arguments: dict[str, Any] = {
            "model": TEXT_MODEL,
            "reasoning": {"effort": "low"},
            "text": {"verbosity": "low"},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Order a short Vietnamese tone drill. You may select only supplied "
                        "inventory IDs. "
                        "Prioritize contrast and recent error history. Do not invent vocabulary."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "theme": request.theme,
                            "size": request.size,
                            "valid_ids": sorted(valid_ids),
                            "history": _sanitized_history(request.history),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text_format": DrillSelection,
            "max_output_tokens": 500,
            "store": False,
        }
        if safety_identifier:
            arguments["safety_identifier"] = safety_identifier
        response = client.responses.parse(**arguments)
        parsed = response.output_parsed
        if parsed is None or not all(item in valid_ids for item in parsed.word_ids):
            return fallback
        return {**parsed.model_dump(), "source": "gpt-5.6-sol"}
    except Exception:
        return fallback
