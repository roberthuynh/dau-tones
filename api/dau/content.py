"""Load Dấu's committed inventory and reference metadata."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

import numpy as np

from .settings import DATA_ROOT, REPO_ROOT, TARGETS_ROOT

TONE_ORDER = ("ngang", "huyen", "sac", "hoi", "nga", "nang")
TONE_FAMILIES = {
    "north": {
        "ngang": "level",
        "huyen": "falling",
        "sac": "rising",
        "hoi": "dipping",
        "nga": "broken_rising",
        "nang": "heavy_falling",
    },
    "south": {
        "ngang": "level",
        "huyen": "falling",
        "sac": "rising",
        "hoi": "dipping",
        "nga": "dipping",
        "nang": "falling",
    },
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def inventory_document() -> dict[str, Any]:
    return cast(
        dict[str, Any], _load_json(DATA_ROOT / "inventory.json", {"tones": [], "words": []})
    )


@lru_cache(maxsize=1)
def echo_document() -> dict[str, Any]:
    """Return the scene course plus flattened compatibility sentence records."""

    legacy = cast(dict[str, Any], _load_json(DATA_ROOT / "echo_sentences.json", {"sentences": []}))
    course = cast(dict[str, Any], _load_json(DATA_ROOT / "echo_scenes.json", {"scenes": []}))
    ordered_scenes = sorted(course.get("scenes", []), key=lambda item: item.get("order", 0))
    flat_source = [(scene, turn) for scene in ordered_scenes for turn in scene.get("turns", [])]
    next_by_id = {
        turn["id"]: flat_source[index + 1][1]["id"] if index + 1 < len(flat_source) else None
        for index, (_, turn) in enumerate(flat_source)
    }
    previous_by_id = {
        turn["id"]: flat_source[index - 1][1]["id"] if index else None
        for index, (_, turn) in enumerate(flat_source)
    }
    scenes: list[dict[str, Any]] = []
    turns: list[dict[str, Any]] = []
    learner_sentences: list[dict[str, Any]] = []
    for scene in ordered_scenes:
        learner_number = 0
        normalized_turns: list[dict[str, Any]] = []
        for turn_index, source_turn in enumerate(scene.get("turns", [])):
            if source_turn.get("speaker") == "learner":
                learner_number += 1
            turn = {
                **source_turn,
                "scene_id": scene["id"],
                "scene_order": scene.get("order"),
                "turn_index": turn_index,
                "learner_turn_number": learner_number
                if source_turn.get("speaker") == "learner"
                else None,
                "role_label": "Thầy Minh" if source_turn.get("speaker") == "minh" else "You",
                "next_turn_id": next_by_id[source_turn["id"]],
                "previous_turn_id": previous_by_id[source_turn["id"]],
                "focus_word_ids": [
                    focus["word_id"]
                    for focus in source_turn.get("focuses", [])
                    if focus.get("word_id")
                ],
            }
            normalized_turns.append(turn)
            turns.append(turn)
            if turn["speaker"] == "learner":
                learner_sentences.append(
                    {
                        **turn,
                        "sentence_id": turn["id"],
                        "theme": scene["id"],
                        "literal_stakes": turn.get("literal_stakes", []),
                    }
                )
        scenes.append({**scene, "turns": normalized_turns})
    return {
        **course,
        "scenes": scenes,
        "turns": turns,
        "sentences": learner_sentences,
        "legacy_sentences": legacy.get("sentences", []),
    }


@lru_cache(maxsize=1)
def demo_document() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        _load_json(DATA_ROOT / "demo_manifest.json", {"analyzer": [], "echo": []}),
    )


@lru_cache(maxsize=1)
def target_manifest() -> dict[str, Any]:
    return cast(dict[str, Any], _load_json(TARGETS_ROOT / "manifest.json", {"targets": []}))


@lru_cache(maxsize=1)
def validated_targets() -> tuple[dict[str, Any], ...]:
    """Return only hash-checked targets that passed, even during a blocked build.

    The final manifest remains all-or-nothing. A blocked generation receipt can
    still improve local templates and demos without promoting any failed take.
    """

    candidates = target_manifest().get("targets", [])
    if not candidates:
        candidates = _load_json(TARGETS_ROOT / "generation-report.json", {}).get("targets", [])
    resolved: list[dict[str, Any]] = []
    for target in candidates:
        relative_path = target.get("path")
        if not isinstance(relative_path, str) or not target.get("validation", {}).get(
            "passed", False
        ):
            continue
        path = REPO_ROOT / relative_path
        expected_hash = target.get("sha256")
        if (
            not path.is_file()
            or not isinstance(expected_hash, str)
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash
        ):
            continue
        resolved.append(target)
    return tuple(resolved)


def reference_corpus_is_complete() -> bool:
    """Return true only when every inventory/accent target passed validation."""

    expected = {
        (word["id"], accent)
        for word in inventory_document().get("words", [])
        for accent in ("north", "south")
    }
    targets = target_manifest().get("targets", [])
    resolved: set[tuple[str, str]] = set()
    for target in targets:
        key = (str(target.get("word_id", "")), str(target.get("accent", "")))
        relative_path = target.get("path")
        if (
            key not in expected
            or not isinstance(relative_path, str)
            or not (REPO_ROOT / relative_path).is_file()
            or not target.get("validation", {}).get("passed", False)
        ):
            return False
        resolved.add(key)
    return bool(expected) and resolved == expected and len(targets) == len(expected)


def generic_contour(tone: str, accent: str = "north") -> list[float]:
    """Return a pedagogical contour while the validated manifest is loading."""

    x = np.linspace(0.0, 1.0, 64)
    if tone == "ngang":
        y = 0.18 * np.sin(math.pi * x)
    elif tone == "huyen":
        y = 1.9 - 4.0 * x + 0.25 * np.sin(math.pi * x)
    elif tone == "sac":
        y = -2.1 + 5.2 * np.power(x, 1.65)
    elif tone == "hoi":
        y = 2.0 - 6.2 * np.sin(math.pi * np.minimum(x, 0.72) / 1.44)
        y += np.where(x > 0.62, 4.1 * (x - 0.62), 0.0)
    elif tone == "nga":
        if accent == "south":
            y = 1.3 - 4.0 * np.sin(math.pi * np.minimum(x, 0.7) / 1.4)
            y += np.where(x > 0.58, 5.0 * (x - 0.58), 0.0)
        else:
            y = -1.0 + 1.3 * x + 2.9 * np.maximum(x - 0.46, 0.0)
            y += np.where((x > 0.43) & (x < 0.54), -0.8, 0.0)
    elif tone == "nang":
        y = 1.2 - 4.2 * np.minimum(x / 0.7, 1.0)
    else:
        y = np.zeros_like(x)
    y = y - float(np.median(y))
    return [round(float(value), 4) for value in y]


def target_for(word_id: str, accent: str) -> dict[str, Any] | None:
    targets = validated_targets()
    return next(
        (
            item
            for item in targets
            if item.get("word_id") == word_id and item.get("accent") == accent
        ),
        None,
    )


def word_by_id(word_id: str) -> dict[str, Any] | None:
    return next(
        (word for word in inventory_document().get("words", []) if word.get("id") == word_id),
        None,
    )


def word_surface(word: dict[str, Any]) -> str:
    return str(word.get("surface") or word.get("syllable") or word["id"])


def public_words() -> dict[str, Any]:
    document = inventory_document()
    evaluation = _load_json(DATA_ROOT / "evaluation.json", {})
    northern_mode = (
        evaluation.get("accents", {}).get("north", {}).get("scoring_mode", "four_family")
    )
    northern_mode = "four_family" if northern_mode not in {"six_tone", "six-tone"} else "six_tone"
    words: list[dict[str, Any]] = []
    for source in document.get("words", []):
        word = dict(source)
        word["surface"] = word_surface(word)
        word["art_url"] = f"/art/{word['id']}.png"
        word["targets"] = {}
        for accent in ("north", "south"):
            target = target_for(word["id"], accent)
            contour = (target or {}).get("contour") or generic_contour(word["tone"], accent)
            word["targets"][accent] = {
                "audio_url": (
                    f"/audio/targets/{accent}/{word['id']}.wav" if target else ""
                ),
                "contour": contour,
                "validated": bool(target and target.get("validation", {}).get("passed", True)),
            }
        words.append(word)
    classifier_document = _load_json(DATA_ROOT / "classifier_profile.json", {})
    return {
        "tones": document.get("tones", []),
        "words": words,
        "featured_queue": document.get("featured_queue", []),
        "minimal_pair_groups": document.get("minimal_pair_groups", []),
        "drills": {item["id"]: item for item in document.get("themed_drills", [])},
        "scoring_modes": {"north": northern_mode, "south": "four_family"},
        "classifier_profiles": classifier_document.get("profiles", {}),
    }


def clear_content_caches() -> None:
    inventory_document.cache_clear()
    echo_document.cache_clear()
    demo_document.cache_clear()
    target_manifest.cache_clear()
    validated_targets.cache_clear()
