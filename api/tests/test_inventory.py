from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path, PurePosixPath

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ASCII_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ACCENT_IDS = {"north", "south"}
TONE_IDS = {"ngang", "huyen", "sac", "hoi", "nga", "nang"}


def load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def walk_strings(value: object):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from walk_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from walk_strings(item)


def assert_safe_relative_path(path: str) -> None:
    parsed = PurePosixPath(path)
    assert not parsed.is_absolute()
    assert ".." not in parsed.parts


def test_all_committed_data_is_nfc() -> None:
    for filename in (
        "inventory.json",
        "echo_sentences.json",
        "echo_scenes.json",
        "demo_manifest.json",
    ):
        for value in walk_strings(load(filename)):
            assert value == unicodedata.normalize("NFC", value), (
                f"{filename} contains a non-NFC string: {value!r}"
            )


def test_inventory_is_balanced_and_uses_stable_ids() -> None:
    data = load("inventory.json")
    words = data["words"]
    ids = [word["id"] for word in words]

    assert data["schema_version"] == 1
    assert len(words) == 19
    assert len(ids) == len(set(ids))
    assert all(ASCII_ID.fullmatch(word_id) for word_id in ids)
    assert Counter(word["tone"] for word in words) == {
        "ngang": 3,
        "huyen": 3,
        "sac": 3,
        "hoi": 3,
        "nga": 3,
        "nang": 4,
    }

    expected_syllables = {
        "ma",
        "mà",
        "má",
        "mả",
        "mã",
        "mạ",
        "Phương",
        "phường",
        "phượng",
        "cơm",
        "nhà",
        "cá",
        "lá",
        "phở",
        "cửa",
        "sữa",
        "mũ",
        "mẹ",
        "bạn",
    }
    assert {word["syllable"] for word in words} == expected_syllables


def test_tone_and_accent_metadata_is_complete() -> None:
    data = load("inventory.json")
    tones = data["tones"]
    accents = data["target_generation"]["accents"]

    assert data["default_accent"] == "north"
    assert data["tone_order"] == ["ngang", "huyen", "sac", "hoi", "nga", "nang"]
    assert {tone["id"] for tone in tones} == TONE_IDS
    assert {accent["id"] for accent in accents} == ACCENT_IDS
    assert data["target_generation"]["voice"] == "cedar"
    assert data["target_generation"]["candidates_per_word"] == 5
    assert data["target_generation"]["carrier_phrase_candidates_on_failure"] == 5

    accent_by_id = {accent["id"]: accent for accent in accents}
    assert accent_by_id["north"]["prompt"].startswith(
        "Always speak natural Vietnamese with a neutral Northern Vietnamese (Hà Nội) accent."
    )
    assert accent_by_id["south"]["prompt"].startswith(
        "Always speak natural Vietnamese with a modern Southern Vietnamese (Sài Gòn) accent."
    )
    assert accent_by_id["south"]["default_scoring_mode"] == "four_family"

    for tone in tones:
        assert set(tone["four_way_family"]) == ACCENT_IDS
        assert tone["css_variable"] == f"--tone-{tone['id']}"
        assert re.fullmatch(r"#[0-9A-F]{6}", tone["color"])


def test_word_metadata_and_audio_contracts_are_complete() -> None:
    data = load("inventory.json")
    for word in data["words"]:
        assert word["tone"] in TONE_IDS
        assert word["meaning_en"]
        assert word["usage_note"].endswith(".")
        assert word["art_concept"]
        assert word["ascii_base"].isascii()
        assert set(word["target_audio"]) == ACCENT_IDS
        for accent, path in word["target_audio"].items():
            assert path == f"targets/{accent}/{word['id']}.wav"
            assert_safe_relative_path(path)


def test_minimal_pair_mappings_are_closed_and_signature_copy_is_exact() -> None:
    data = load("inventory.json")
    words = {word["id"]: word for word in data["words"]}
    groups = {group["id"]: group for group in data["minimal_pair_groups"]}

    assert set(groups) == {"ma-six-tones", "phuong-six-tones"}
    for group_id, group in groups.items():
        assert ASCII_ID.fullmatch(group_id)
        members = {form["word_id"] for form in group["forms"] if form["word_id"]}
        assert members <= words.keys()
        for word_id in members:
            word = words[word_id]
            assert word["minimal_pair_group"] == group_id
            assert set(word["minimal_pair_ids"]) == members - {word_id}
        assert {form["tone"] for form in group["forms"]} == TONE_IDS

    phuong_forms = {form["tone"]: form for form in groups["phuong-six-tones"]["forms"]}
    assert phuong_forms["nang"] == {
        "tone": "nang",
        "surface": "phượng",
        "word_id": "phuong-phoenix",
        "meaning_en": "phoenix",
    }
    assert all(
        phuong_forms[tone]["word_id"] is None
        for tone in ("sac", "hoi", "nga")
    )

    phuong = words["phuong-name"]
    assert phuong["syllable"] == "Phương"
    assert "phương can also mean direction" in phuong["usage_note"]
    assert "not a claim about the name's etymology" in phuong["usage_note"]
    assert "compass" in phuong["art_concept"]

    overrides = {
        (item["intended_word_id"], item["detected_word_id"]): item["copy"]
        for item in data["verdict_overrides"]
    }
    assert overrides[("phuong-name", "phuong-ward")] == (
        "You meant Phương, the name. You said phường, an urban ward."
    )


def test_featured_queue_and_fallback_drills_only_reference_inventory() -> None:
    data = load("inventory.json")
    word_ids = {word["id"] for word in data["words"]}
    queue = data["featured_queue"]

    assert queue[:9] == [
        "ma-ghost",
        "ma-but",
        "ma-mother",
        "ma-grave",
        "ma-code",
        "ma-seedling",
        "phuong-name",
        "phuong-ward",
        "phuong-phoenix",
    ]
    assert len(queue) == len(word_ids)
    assert set(queue) == word_ids

    themes = {drill["id"]: drill for drill in data["themed_drills"]}
    assert set(themes) == {"food", "family", "travel"}
    tone_by_word = {word["id"]: word["tone"] for word in data["words"]}
    for drill in themes.values():
        assert len(drill["word_ids"]) == len(set(drill["word_ids"]))
        assert set(drill["word_ids"]) <= word_ids
        assert len({tone_by_word[word_id] for word_id in drill["word_ids"]}) >= 4


def test_echo_sentence_contract_and_literal_stakes() -> None:
    inventory = load("inventory.json")
    word_ids = {word["id"] for word in inventory["words"]}
    data = load("echo_sentences.json")
    sentences = data["sentences"]

    assert len(sentences) == 8
    assert [sentence["text"] for sentence in sentences] == [
        "Xin chào!",
        "Cảm ơn bạn.",
        "Bạn khỏe không?",
        "Mẹ tôi tên là Phương.",
        "Tối nay con mời má đi ăn cơm.",
        "Cho tôi một tô phở.",
        "Cho tôi một ly nước.",
        "Nhà vệ sinh ở đâu?",
    ]
    assert len({sentence["id"] for sentence in sentences}) == 8

    stakes = []
    for sentence in sentences:
        assert ASCII_ID.fullmatch(sentence["id"])
        assert set(sentence["focus_word_ids"]) <= word_ids
        assert set(sentence["shadow_audio"]) == ACCENT_IDS
        for accent, path in sentence["shadow_audio"].items():
            assert path == f"targets/echo/{accent}/{sentence['id']}.wav"
            assert_safe_relative_path(path)
        stakes.extend(sentence["literal_stakes"])

    assert len(stakes) == 2
    for stake in stakes:
        assert stake["intended_word_id"] in word_ids
        assert stake["heard_word_id"] in word_ids
    assert any("invited a ghost to dinner" in stake["explanation"] for stake in stakes)


def test_demo_manifest_references_canonical_ids_and_safe_paths() -> None:
    inventory = load("inventory.json")
    word_ids = {word["id"] for word in inventory["words"]}
    tones = {tone["id"] for tone in inventory["tones"]}
    legacy_echo = load("echo_sentences.json")
    scene_echo = load("echo_scenes.json")
    sentence_ids = {sentence["id"] for sentence in legacy_echo["sentences"]}
    turn_ids = {
        turn["id"] for scene in scene_echo["scenes"] for turn in scene["turns"]
    }
    demos = load("demo_manifest.json")

    assert [demo["id"] for demo in demos["analyzer_demos"]] == [
        "ma-mother-correct",
        "ma-mother-said-ghost",
        "phuong-name-said-ward",
    ]
    for demo in demos["analyzer_demos"]:
        assert ASCII_ID.fullmatch(demo["id"])
        assert demo["accent"] in ACCENT_IDS
        assert demo["intended_word_id"] in word_ids
        assert demo["expected_detected_word_id"] in word_ids
        assert demo["expected_detected_tone"] in tones
        assert_safe_relative_path(demo["recording_path"])

    assert len(demos["echo_demos"]) >= 1
    for demo in demos["echo_demos"]:
        assert ASCII_ID.fullmatch(demo["id"])
        assert demo["sentence_id"] in sentence_ids | turn_ids
        assert demo["accent"] in ACCENT_IDS
        assert_safe_relative_path(demo["recording_path"])
        for divergence in demo.get("expected_divergences", []):
            assert divergence["kind"] in {"tone_only", "lexical", "missing", "extra"}
            assert divergence["intended_word_id"] in word_ids
            assert divergence["heard_word_id"] in word_ids
        if "scene_id" in demo:
            assert demo["turn_id"] in turn_ids
            assert demo["generation"]["validation"]["selected"]["passed"] is True


def test_data_never_names_the_deprecated_tts_model() -> None:
    serialized = "\n".join(
        (DATA_DIR / name).read_text(encoding="utf-8")
        for name in (
            "inventory.json",
            "echo_sentences.json",
            "echo_scenes.json",
            "demo_manifest.json",
        )
    )
    assert "gpt-4o-mini-tts" not in serialized
