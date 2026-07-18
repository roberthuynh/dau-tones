from __future__ import annotations

import unicodedata

from dau.echo import (
    align_transcript,
    detected_tone_metadata,
    literal_explanation,
    meaning_status,
    normalize_text,
    practice_word_ids,
    strip_tone_marks,
    tone_id,
)
from scripts.validate_echo_course import validate_course


def test_tone_only_alignment_preserves_literal_meanings() -> None:
    diff = align_transcript(
        "Tối nay con mời má đi ăn cơm.",
        "Tối nay con mời ma đi ăn cơm.",
    )
    changed = [item for item in diff if item["kind"] != "match"]
    assert len(changed) == 1
    expected = {
        "target": "má",
        "heard": "ma",
        "kind": "tone_only",
        "target_word_id": "ma-mother",
        "heard_word_id": "ma-ghost",
        "meaning_explanation": "You said ma (ghost) instead of má (mother).",
    }
    assert all(changed[0][key] == value for key, value in expected.items())
    assert changed[0]["target_index"] == changed[0]["heard_index"] == 4
    assert changed[0]["target_tone"] == "sac"
    assert changed[0]["heard_tone"] == "ngang"
    assert changed[0]["semantic_status"] == "known_word"
    assert practice_word_ids(diff) == ["ma-mother"]
    assert meaning_status(diff) == "known_word_change"
    assert detected_tone_metadata(diff)[0]["detected_tone"] == "ngang"
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
    assert tone_id("mà") == "huyen"
    assert tone_id("Phượng") == "nang"


def test_unknown_tone_form_never_invents_a_meaning() -> None:
    diff = align_transcript("Phương", "phưỡng")
    changed = [item for item in diff if item["kind"] != "match"]
    assert changed[0]["semantic_status"] == "no_known_meaning"
    assert changed[0]["heard_tone"] == "nga"
    assert changed[0]["heard_word_id"] is None
    assert "no curated meaning" in changed[0]["meaning_explanation"]
    assert meaning_status(diff) == "no_known_meaning"


def test_repeated_token_alignment_keeps_the_changed_occurrence() -> None:
    target = "Tôi không gọi thêm cơm, nhưng cho tôi một đĩa cá nhỏ."
    heard = "Tôi không gọi thêm cơm, nhưng cho tối một đĩa cá nhỏ."
    changed = [item for item in align_transcript(target, heard) if item["kind"] != "match"]
    assert len(changed) == 1
    assert changed[0]["target"] == "tôi"
    assert changed[0]["heard"] == "tối"
    assert changed[0]["target_index"] == changed[0]["heard_index"] == 7


def test_echo_course_contract_is_complete() -> None:
    assert validate_course() == {
        "scenes": 4,
        "turns": 26,
        "learner_turns": 13,
        "focuses": 44,
        "offline_demos": 4,
        "dual_accent_wavs_expected": 52,
    }
