"""Vietnamese transcript alignment and literal meaning feedback."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Literal

from .content import inventory_document, word_surface

TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
TONE_MARKS = {
    "\u0300": "huyen",
    "\u0301": "sac",
    "\u0309": "hoi",
    "\u0303": "nga",
    "\u0323": "nang",
}
TONE_LABELS_VI = {
    "ngang": "không dấu",
    "huyen": "dấu huyền",
    "sac": "dấu sắc",
    "hoi": "dấu hỏi",
    "nga": "dấu ngã",
    "nang": "dấu nặng",
}


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold().strip()


def tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(normalize_text(value))


def strip_tone_marks(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value)
    tone_marks = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}
    return unicodedata.normalize(
        "NFC", "".join(char for char in decomposed if char not in tone_marks)
    )


def tone_id(value: str) -> str:
    """Read the Vietnamese lexical tone encoded in one orthographic token."""

    for char in unicodedata.normalize("NFD", value):
        tone = TONE_MARKS.get(char)
        if tone:
            return tone
    return "ngang"


def _word_lookup() -> dict[str, dict[str, Any]]:
    return {
        normalize_text(word_surface(word)): word for word in inventory_document().get("words", [])
    }


def align_transcript(target: str, heard: str) -> list[dict[str, Any]]:
    expected = tokens(target)
    actual = tokens(heard)
    lookup = _word_lookup()
    output: list[dict[str, Any]] = []
    matcher = SequenceMatcher(a=expected, b=actual, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            output.extend(
                {
                    "target": token,
                    "heard": token,
                    "kind": "match",
                    "target_index": target_index,
                    "heard_index": j1 + (target_index - i1),
                    "target_tone": tone_id(token),
                    "heard_tone": tone_id(token),
                    "semantic_status": "match",
                }
                for target_index, token in enumerate(expected[i1:i2], start=i1)
            )
            continue
        if tag == "delete":
            output.extend(
                {
                    "target": token,
                    "heard": None,
                    "kind": "missing",
                    "target_index": target_index,
                    "heard_index": None,
                    "target_tone": tone_id(token),
                    "heard_tone": None,
                    "semantic_status": "not_applicable",
                }
                for target_index, token in enumerate(expected[i1:i2], start=i1)
            )
            continue
        if tag == "insert":
            output.extend(
                {
                    "target": None,
                    "heard": token,
                    "kind": "extra",
                    "target_index": None,
                    "heard_index": heard_index,
                    "target_tone": None,
                    "heard_tone": tone_id(token),
                    "semantic_status": "not_applicable",
                }
                for heard_index, token in enumerate(actual[j1:j2], start=j1)
            )
            continue
        width = max(i2 - i1, j2 - j1)
        for offset in range(width):
            target_token = expected[i1 + offset] if i1 + offset < i2 else None
            heard_token = actual[j1 + offset] if j1 + offset < j2 else None
            kind = "lexical"
            if (
                target_token
                and heard_token
                and strip_tone_marks(target_token) == strip_tone_marks(heard_token)
            ):
                kind = "tone_only"
            target_word = lookup.get(target_token or "")
            heard_word = lookup.get(heard_token or "")
            item: dict[str, Any] = {
                "target": target_token,
                "heard": heard_token,
                "kind": kind,
                "target_index": i1 + offset if target_token is not None else None,
                "heard_index": j1 + offset if heard_token is not None else None,
                "target_word_id": (target_word or {}).get("id"),
                "heard_word_id": (heard_word or {}).get("id"),
                "target_tone": tone_id(target_token) if target_token else None,
                "heard_tone": tone_id(heard_token) if heard_token else None,
                "semantic_status": "lexical_change",
            }
            if kind == "tone_only":
                if target_word and heard_word:
                    item["semantic_status"] = "known_word"
                    item["meaning_explanation"] = (
                        f"You said {word_surface(heard_word)} ({heard_word['meaning_en']}) "
                        f"instead of {word_surface(target_word)} ({target_word['meaning_en']})."
                    )
                elif heard_word:
                    item["semantic_status"] = "known_word"
                    item["meaning_explanation"] = (
                        f"Dấu heard {word_surface(heard_word)} ({heard_word['meaning_en']}) "
                        f"instead of {target_token}."
                    )
                else:
                    item["semantic_status"] = "no_known_meaning"
                    intended = word_surface(target_word) if target_word else target_token
                    heard_tone = str(item["heard_tone"])
                    item["meaning_explanation"] = (
                        f"Dấu heard {TONE_LABELS_VI[heard_tone]} on “{intended}.” "
                        "That form has no curated meaning in this lesson."
                    )
            output.append(item)
    return output


def practice_word_ids(diff: list[dict[str, Any]]) -> list[str]:
    """Return stable Tone Lab destinations for changed target words."""

    return list(
        dict.fromkeys(
            str(item["target_word_id"])
            for item in diff
            if item.get("kind") != "match" and item.get("target_word_id")
        )
    )


def detected_tone_metadata(diff: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose tone-only changes without treating lexical ASR edits as pitch evidence."""

    return [
        {
            "token_index": item["target_index"],
            "target": item["target"],
            "heard": item["heard"],
            "intended_tone": item["target_tone"],
            "detected_tone": item["heard_tone"],
            "target_word_id": item.get("target_word_id"),
            "heard_word_id": item.get("heard_word_id"),
            "semantic_status": item["semantic_status"],
        }
        for item in diff
        if item.get("kind") == "tone_only"
        and item.get("target_index") is not None
        and item.get("target")
        and item.get("heard")
    ]


def meaning_status(
    diff: list[dict[str, Any]],
) -> Literal[
    "exact_match",
    "known_word_change",
    "no_known_meaning",
    "lexical_change",
    "missing_or_extra",
]:
    """Summarize transcript semantics for the reveal state."""

    changed = [item for item in diff if item.get("kind") != "match"]
    if not changed:
        return "exact_match"
    if any(item.get("semantic_status") == "known_word" for item in changed):
        return "known_word_change"
    if any(item.get("semantic_status") == "no_known_meaning" for item in changed):
        return "no_known_meaning"
    if any(item.get("kind") in {"missing", "extra"} for item in changed):
        return "missing_or_extra"
    return "lexical_change"


def literal_explanation(diff: list[dict[str, Any]]) -> str:
    explained = [
        str(item["meaning_explanation"]) for item in diff if item.get("meaning_explanation")
    ]
    if explained:
        first = explained[0]
        if "ma (ghost)" in first and "má" in first:
            return f"{first} That turns a family dinner into an invitation for a ghost."
        return first
    if any(item.get("kind") != "match" for item in diff):
        return (
            "The transcript changed, but Dấu only assigns a literal meaning when the pair "
            "is in its curated lexicon."
        )
    return "Every word matched the target transcript."
