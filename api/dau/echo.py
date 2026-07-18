"""Vietnamese transcript alignment and literal meaning feedback."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .content import inventory_document, word_surface

TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


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
                {"target": token, "heard": token, "kind": "match"} for token in expected[i1:i2]
            )
            continue
        if tag == "delete":
            output.extend(
                {"target": token, "heard": None, "kind": "missing"} for token in expected[i1:i2]
            )
            continue
        if tag == "insert":
            output.extend(
                {"target": None, "heard": token, "kind": "extra"} for token in actual[j1:j2]
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
                kind = "tone"
            target_word = lookup.get(target_token or "")
            heard_word = lookup.get(heard_token or "")
            item: dict[str, Any] = {
                "target": target_token,
                "heard": heard_token,
                "kind": kind,
                "target_word_id": (target_word or {}).get("id"),
                "heard_word_id": (heard_word or {}).get("id"),
            }
            if kind == "tone" and target_word and heard_word:
                item["meaning_explanation"] = (
                    f"You said {word_surface(heard_word)} ({heard_word['meaning_en']}) "
                    f"instead of {word_surface(target_word)} ({target_word['meaning_en']})."
                )
            output.append(item)
    return output


def literal_explanation(diff: list[dict[str, Any]]) -> str:
    explained = [
        item.get("meaning_explanation") for item in diff if item.get("meaning_explanation")
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
