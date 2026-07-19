"""Validate hashes and cross-file contracts for every committed release asset."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from dau.models import IMAGE_MODEL, REFERENCE_MODEL, SPEECH_MODEL

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCENTS = ("north", "south")


class ReleaseValidationError(ValueError):
    """A committed release receipt does not match its files or curriculum."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseValidationError(message)


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.relative_to(REPO_ROOT)} must contain an object")
    return cast(dict[str, Any], value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_file(relative: str) -> Path:
    candidate = (REPO_ROOT / relative).resolve()
    _require(
        candidate.is_relative_to(REPO_ROOT),
        f"release asset escapes the repository: {relative}",
    )
    _require(candidate.is_file(), f"release asset is missing: {relative}")
    return candidate


def _verified_file(relative: str, expected_hash: str) -> Path:
    path = _repo_file(relative)
    actual = _sha256(path)
    _require(actual == expected_hash, f"SHA-256 mismatch for {relative}: {actual}")
    return path


def _validate_prompt_hash(record: Mapping[str, Any], label: str) -> None:
    prompt = record.get("prompt")
    expected = record.get("prompt_sha256")
    _require(isinstance(prompt, str) and bool(prompt), f"{label} has no generation prompt")
    _require(isinstance(expected, str), f"{label} has no prompt SHA-256")
    assert isinstance(prompt, str)
    actual = hashlib.sha256(prompt.encode()).hexdigest()
    _require(actual == expected, f"prompt SHA-256 mismatch for {label}")


def _validate_word_art(word_ids: set[str]) -> int:
    manifest = _object(REPO_ROOT / "web/public/art/manifest.json")
    records = manifest.get("images", [])
    _require(isinstance(records, list), "meaning-art manifest images must be a list")
    by_id = {str(record.get("word_id")): record for record in records}
    _require(set(by_id) == word_ids, "meaning-art IDs do not exactly match the inventory")
    for word_id, record in by_id.items():
        _require(record.get("model") == IMAGE_MODEL, f"{word_id} uses an unapproved image model")
        _require(record.get("size") == "1024x1024", f"{word_id} art is not 1024x1024")
        _require(record.get("quality") == "medium", f"{word_id} art is not medium quality")
        _validate_prompt_hash(record, f"meaning art {word_id}")
        _verified_file(f"web/public/art/{word_id}.png", str(record.get("file_sha256", "")))
    return len(records)


def _validate_scene_art(scenes: Sequence[Mapping[str, Any]]) -> int:
    manifest = _object(REPO_ROOT / "web/public/art/scenes/manifest.json")
    records = manifest.get("assets", [])
    _require(isinstance(records, list), "scene-art manifest assets must be a list")
    expected_files: set[str] = set()
    for scene in scenes:
        expected_files.add(Path(str(scene.get("art_url", ""))).name)
        demo = scene.get("offline_demo", {})
        if isinstance(demo, Mapping) and demo.get("mistake_art_url"):
            expected_files.add(Path(str(demo["mistake_art_url"])).name)
    by_file = {str(record.get("file")): record for record in records}
    _require(expected_files <= set(by_file), "scene or demo art is missing from the scene manifest")
    _require(len(by_file) == 7, "scene-art manifest must contain four scenes and three mistakes")
    for filename, record in by_file.items():
        _require(record.get("model") == IMAGE_MODEL, f"{filename} uses an unapproved image model")
        _validate_prompt_hash(record, f"scene art {filename}")
        path = _verified_file(
            f"web/public/art/scenes/{filename}", str(record.get("file_sha256", ""))
        )
        _require(path.stat().st_size == record.get("bytes"), f"byte count mismatch for {filename}")
    contact_sheet = manifest.get("contact_sheet")
    _require(
        isinstance(contact_sheet, str) and bool(contact_sheet),
        "scene-art manifest has no contact sheet",
    )
    _repo_file(f"web/public/art/scenes/{contact_sheet}")
    return len(records)


def _validate_targets(word_ids: set[str]) -> tuple[int, int]:
    report = _object(REPO_ROOT / "targets/generation-report.json")
    targets = report.get("targets", [])
    failures = report.get("failures", [])
    _require(
        isinstance(targets, list) and isinstance(failures, list),
        "target receipt is malformed",
    )
    expected = {f"{accent}/{word_id}" for accent in ACCENTS for word_id in word_ids}
    accepted: set[str] = set()
    for target in targets:
        pair = f"{target.get('accent')}/{target.get('word_id')}"
        _require(pair not in accepted, f"duplicate accepted target {pair}")
        accepted.add(pair)
        _require(target.get("model") in {REFERENCE_MODEL, None}, f"{pair} uses an invalid model")
        _require(
            target.get("validation", {}).get("passed") is True,
            f"{pair} did not pass validation",
        )
        _require(len(target.get("contour", [])) == 64, f"{pair} has no 64-point contour")
        path = _verified_file(str(target.get("path", "")), str(target.get("sha256", "")))
        public = REPO_ROOT / "web/public/audio/targets" / str(target.get("accent")) / path.name
        _require(public.is_file(), f"static target copy is missing for {pair}")
        _require(_sha256(public) == _sha256(path), f"static target copy differs for {pair}")

    failed = {str(item.get("pair_id")) for item in failures}
    _require(not (accepted & failed), "target receipt contains accepted/failed overlap")
    _require(
        accepted | failed == expected,
        "target receipt does not account for all inventory pairs",
    )
    complete = not failed
    _require(
        report.get("status") == ("complete" if complete else "blocked"),
        "target report status does not match its failures",
    )

    profile = _object(REPO_ROOT / "api/data/classifier_profile.json")
    _require(bool(profile.get("corpus_complete")) == complete, "classifier corpus status drifted")
    _require(
        set(profile.get("missing_target_ids", [])) == failed,
        "classifier missing-target IDs drifted",
    )

    final_manifest = REPO_ROOT / "targets/manifest.json"
    if complete:
        _require(final_manifest.is_file(), "complete corpus has no final target manifest")
        promoted = _object(final_manifest).get("targets", [])
        _require(len(promoted) == len(expected), "final target manifest is incomplete")
    else:
        _require(not final_manifest.exists(), "blocked corpus must not publish a target manifest")
    return len(accepted), len(failed)


def _validate_echo_audio(scenes: Sequence[Mapping[str, Any]]) -> int:
    manifest = _object(REPO_ROOT / "targets/echo/manifest.json")
    records = manifest.get("utterances", [])
    _require(isinstance(records, list), "Dialogue audio manifest utterances must be a list")
    turn_ids = {
        str(turn.get("id"))
        for scene in scenes
        for turn in scene.get("turns", [])
        if isinstance(turn, Mapping)
    }
    expected = {(accent, turn_id) for accent in ACCENTS for turn_id in turn_ids}
    actual: set[tuple[str, str]] = set()
    for record in records:
        identity = (str(record.get("accent")), str(record.get("turn_id")))
        _require(identity not in actual, f"duplicate Dialogue audio {identity}")
        actual.add(identity)
        _require(
            record.get("model") in {SPEECH_MODEL, REFERENCE_MODEL},
            f"invalid model for {identity}",
        )
        selected = record.get("validation", {}).get("selected", {})
        _require(selected.get("passed") is True, f"Dialogue audio did not pass: {identity}")
        source = _verified_file(str(record.get("path", "")), str(record.get("sha256", "")))
        public = REPO_ROOT / "web/public/audio/echo" / identity[0] / source.name
        _require(public.is_file(), f"static Dialogue copy is missing for {identity}")
        _require(_sha256(public) == _sha256(source), f"static Dialogue copy differs for {identity}")
    _require(actual == expected, "Dialogue audio does not exactly cover every turn and accent")
    _require(
        manifest.get("expected_utterance_count") == len(expected),
        "Dialogue expected count drifted",
    )
    return len(records)


def _validate_demos() -> int:
    manifest = _object(REPO_ROOT / "api/data/demo_manifest.json")
    records = list(manifest.get("analyzer_demos", [])) + list(manifest.get("echo_demos", []))
    identities: set[str] = set()
    for record in records:
        demo_id = str(record.get("id"))
        _require(demo_id not in identities, f"duplicate demo ID {demo_id}")
        identities.add(demo_id)
        _verified_file(str(record.get("recording_path", "")), str(record.get("sha256", "")))
    return len(records)


def validate_release() -> dict[str, int]:
    inventory = _object(REPO_ROOT / "api/data/inventory.json")
    words = inventory.get("words", [])
    _require(isinstance(words, list) and bool(words), "inventory has no words")
    word_ids = {str(word.get("id")) for word in words}
    _require(len(word_ids) == len(words), "inventory word IDs are empty or duplicated")

    course = _object(REPO_ROOT / "api/data/echo_scenes.json")
    scenes = course.get("scenes", [])
    _require(isinstance(scenes, list) and len(scenes) == 4, "release requires four Dialogue scenes")

    accepted_targets, missing_targets = _validate_targets(word_ids)
    return {
        "words": len(words),
        "meaning_art": _validate_word_art(word_ids),
        "scenes": len(scenes),
        "scene_art": _validate_scene_art(scenes),
        "dialogue_audio": _validate_echo_audio(scenes),
        "demos": _validate_demos(),
        "accepted_targets": accepted_targets,
        "missing_targets": missing_targets,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable counts")
    arguments = parser.parse_args()
    try:
        result = validate_release()
    except (OSError, json.JSONDecodeError, ReleaseValidationError) as error:
        parser.exit(1, f"release validation failed: {error}\n")
    if arguments.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(
            "Release assets validated: "
            + ", ".join(f"{name}={count}" for name, count in result.items())
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
