from __future__ import annotations

import unicodedata

from dau.echo import align_transcript, literal_explanation, normalize_text, strip_tone_marks


def test_tone_only_alignment_preserves_literal_meanings() -> None:
    diff = align_transcript(
        "Tối nay con mời má đi ăn cơm.",
        "Tối nay con mời ma đi ăn cơm.",
    )
    changed = [item for item in diff if item["kind"] != "match"]
    assert changed == [
        {
            "target": "má",
            "heard": "ma",
            "kind": "tone_only",
            "target_word_id": "ma-mother",
            "heard_word_id": "ma-ghost",
            "meaning_explanation": "You said ma (ghost) instead of má (mother).",
        }
    ]
    assert "ghost" in literal_explanation(diff)


def test_phuong_name_alignment_is_case_insensitive() -> None:
    diff = align_transcript("Mẹ tôi tên là Phương.", "Mẹ tôi tên là phường.")
    changed = [item for item in diff if item["kind"] != "match"]
    assert changed[0]["kind"] == "tone_only"
    assert changed[0]["target_word_id"] == "phuong-name"
    assert changed[0]["heard_word_id"] == "phuong-ward"


def test_missing_and_extra_words_are_explicit() -> None:
    missing = align_transcript("Xin chào bạn", "Xin chào")
    extra = align_transcript("Xin chào", "Xin chào bạn")
    assert missing[-1]["kind"] == "missing"
    assert extra[-1]["kind"] == "extra"


def test_unicode_helpers_return_nfc() -> None:
    decomposed = unicodedata.normalize("NFD", "Phương")
    assert unicodedata.is_normalized("NFC", normalize_text(decomposed))
    assert strip_tone_marks("mã") == "ma"
    assert strip_tone_marks("mẹ") == "me"
