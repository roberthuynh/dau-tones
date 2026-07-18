"""Specific tone coaching with a deterministic offline contract."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from openai import OpenAI

from .content import inventory_document, word_by_id
from .models import TEXT_MODEL
from .schemas import CoachRequest, CoachResponse, DrillRequest, DrillSelection
from .settings import AI_TIMEOUT_SECONDS, openai_api_key

PHYSICAL_TIPS = {
    "started_too_high": "Start lower, then let the pitch travel into the tone.",
    "started_too_low": "Begin a little higher so the tone has room to move.",
    "no_final_rise": "Keep the vowel open and lift your chin through the final rise.",
    "fell_instead_of_level": "Hold your chin still and carry the pitch straight through the vowel.",
    "too_flat": "Give the vowel more pitch movement instead of holding it in one place.",
    "dip_too_early": "Delay the dip until the middle of the vowel, then recover smoothly.",
    "dip_too_late": "Let the pitch turn downward earlier, around the middle of the vowel.",
    "missing_dip": "Drop into the middle of the vowel before you bring the pitch back up.",
    "too_long": "Make the syllable shorter and close the sound firmly at the end.",
    "too_short": "Give the vowel a little more time so the full contour can appear.",
    "weak_glottal_break": (
        "Briefly tighten at the throat in the middle, then release into the rise."
    ),
    "needs_retry": "Try once more in a quiet breath, holding the phone about a hand away.",
}


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
    return codes


def _next_word(request: CoachRequest) -> tuple[str, str]:
    document = inventory_document()
    featured = document.get("featured_queue", [])
    current = str(request.verdict.get("word") or request.verdict.get("word_id") or "phuong")
    errors = [
        str(item.get("intended_tone"))
        for item in request.history[-12:]
        if item.get("correct") is False and item.get("intended_tone")
    ]
    tone = Counter(errors).most_common(1)[0][0] if errors else request.verdict.get("tone_intended")
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
        coaching_sentence=sentence,
        next_word=next_id,
        rationale=rationale,
        source="rules",
    )


def coach(request: CoachRequest) -> CoachResponse:
    fallback = deterministic_coach(request)
    key = openai_api_key()
    if not key:
        return fallback
    valid_ids = [word["id"] for word in inventory_document().get("words", [])]
    try:
        client = OpenAI(api_key=key, timeout=AI_TIMEOUT_SECONDS, max_retries=0)
        response = client.responses.parse(
            model=TEXT_MODEL,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an encouraging, precise Vietnamese tone coach for heritage "
                        "learners. Give exactly one concrete physical instruction, never generic "
                        "praise. Select the next word only from the supplied IDs and explain the "
                        "selection in one short visible rationale."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "verdict": request.verdict,
                            "recent_history": request.history[-12:],
                            "accent": request.accent,
                            "valid_word_ids": valid_ids,
                            "offline_suggestion": fallback.model_dump(),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=CoachResponse,
            max_output_tokens=180,
        )
        parsed = response.output_parsed
        if (
            parsed is None
            or parsed.next_word not in valid_ids
            or word_by_id(parsed.next_word) is None
        ):
            return fallback
        parsed.source = "gpt-5.6-sol"
        return parsed
    except Exception:
        return fallback


def generate_drill(request: DrillRequest) -> dict[str, Any]:
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
        client = OpenAI(api_key=key, timeout=AI_TIMEOUT_SECONDS, max_retries=0)
        response = client.responses.parse(
            model=TEXT_MODEL,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            input=[
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
                            "history": request.history[-12:],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=DrillSelection,
            max_output_tokens=160,
        )
        parsed = response.output_parsed
        if parsed is None or not all(item in valid_ids for item in parsed.word_ids):
            return fallback
        return {**parsed.model_dump(), "source": "gpt-5.6-sol"}
    except Exception:
        return fallback
