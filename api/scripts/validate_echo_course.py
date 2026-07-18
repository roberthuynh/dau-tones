"""Validate the committed Echo dialogue curriculum without loading audio libraries."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

API_ROOT = Path(__file__).resolve().parents[1]
SCENES_PATH = API_ROOT / "data" / "echo_scenes.json"
INVENTORY_PATH = API_ROOT / "data" / "inventory.json"
TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
ACCENTS = {"north", "south"}


def _tokens(value: str) -> list[str]:
    return TOKEN_RE.findall(unicodedata.normalize("NFC", value).casefold())


def _tone_id(value: str) -> str:
    marks = {
        "\u0300": "huyen",
        "\u0301": "sac",
        "\u0309": "hoi",
        "\u0303": "nga",
        "\u0323": "nang",
    }
    for char in unicodedata.normalize("NFD", value):
        if char in marks:
            return marks[char]
    return "ngang"


def validate_course(
    scenes_path: Path = SCENES_PATH,
    inventory_path: Path = INVENTORY_PATH,
) -> dict[str, int]:
    document = json.loads(scenes_path.read_text(encoding="utf-8"))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    words = {word["id"]: word for word in inventory.get("words", [])}
    scenes = document.get("scenes", [])
    if len(scenes) != 4:
        raise ValueError(f"Echo needs exactly four linked scenes, found {len(scenes)}")

    scene_ids: set[str] = set()
    turn_ids: set[str] = set()
    demo_ids: set[str] = set()
    learner_count = 0
    focus_count = 0
    for expected_order, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("id", ""))
        if not scene_id or scene_id in scene_ids:
            raise ValueError(f"Scene ID is missing or duplicated: {scene_id!r}")
        scene_ids.add(scene_id)
        if scene.get("order") != expected_order:
            raise ValueError(f"{scene_id} must have order {expected_order}")
        turns = scene.get("turns", [])
        if not turns or turns[0].get("speaker") != "minh":
            raise ValueError(f"{scene_id} must begin with a Thầy Minh turn")
        for turn_index, turn in enumerate(turns):
            turn_id = str(turn.get("id", ""))
            expected_speaker = "minh" if turn_index % 2 == 0 else "learner"
            if turn.get("speaker") != expected_speaker:
                raise ValueError(f"{turn_id} breaks alternating dialogue roles")
            if not turn_id or turn_id in turn_ids:
                raise ValueError(f"Turn ID is missing or duplicated: {turn_id!r}")
            turn_ids.add(turn_id)
            utterance_tokens = _tokens(str(turn.get("text", "")))
            if turn.get("speaker") == "learner":
                learner_count += 1
                if len(utterance_tokens) < 7:
                    raise ValueError(f"{turn_id} has fewer than seven learner tokens")
            focuses = turn.get("focuses", [])
            if not focuses:
                raise ValueError(f"{turn_id} needs an explicit contour focus")
            for focus in focuses:
                focus_count += 1
                token_index = focus.get("token_index")
                if not isinstance(token_index, int) or not 0 <= token_index < len(utterance_tokens):
                    raise ValueError(f"{turn_id} has an invalid focus index: {token_index}")
                actual = utterance_tokens[token_index]
                expected = unicodedata.normalize("NFC", str(focus.get("token", ""))).casefold()
                if actual != expected:
                    raise ValueError(
                        f"{turn_id} focus {token_index} says {expected!r}, token is {actual!r}"
                    )
                if focus.get("tone") != _tone_id(actual):
                    raise ValueError(f"{turn_id} focus {actual!r} has the wrong tone ID")
                word_id = focus.get("word_id")
                if word_id and word_id not in words:
                    raise ValueError(f"{turn_id} references unknown practice word {word_id}")
            shadow_audio = turn.get("shadow_audio", {})
            if set(shadow_audio) != ACCENTS:
                raise ValueError(f"{turn_id} must declare both accent recordings")
            for accent, path in shadow_audio.items():
                expected_path = f"targets/echo/{accent}/{turn_id}.wav"
                if path != expected_path:
                    raise ValueError(f"{turn_id} audio path must be {expected_path}")

        demo = scene.get("offline_demo", {})
        demo_id = str(demo.get("id", ""))
        if not demo_id or demo_id in demo_ids:
            raise ValueError(f"Offline demo ID is missing or duplicated: {demo_id!r}")
        demo_ids.add(demo_id)
        target_turn = next((turn for turn in turns if turn.get("id") == demo.get("turn_id")), None)
        if not target_turn or target_turn.get("speaker") != "learner":
            raise ValueError(f"{demo_id} must target a learner turn in its own scene")
        target_tokens = _tokens(target_turn["text"])
        heard_tokens = _tokens(str(demo.get("committed_transcript", "")))
        if len(target_tokens) != len(heard_tokens):
            raise ValueError(f"{demo_id} must preserve token count for a tone-only fixture")
        if not any(
            target != heard and _strip_tone(target) == _strip_tone(heard)
            for target, heard in zip(target_tokens, heard_tokens, strict=True)
        ):
            raise ValueError(f"{demo_id} needs at least one tone-only divergence")

    if len(turn_ids) != 26 or learner_count != 13:
        raise ValueError(
            f"Echo needs 26 turns and 13 learner lines, found {len(turn_ids)} and {learner_count}"
        )
    return {
        "scenes": len(scene_ids),
        "turns": len(turn_ids),
        "learner_turns": learner_count,
        "focuses": focus_count,
        "offline_demos": len(demo_ids),
        "dual_accent_wavs_expected": len(turn_ids) * 2,
    }


def _strip_tone(value: str) -> str:
    tone_marks = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}
    return unicodedata.normalize(
        "NFC",
        "".join(char for char in unicodedata.normalize("NFD", value) if char not in tone_marks),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print machine-readable counts")
    args = parser.parse_args()
    receipt: dict[str, Any] = validate_course()
    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "Echo course valid: "
            f"{receipt['scenes']} scenes, {receipt['turns']} turns, "
            f"{receipt['learner_turns']} learner lines, "
            f"{receipt['dual_accent_wavs_expected']} expected WAVs"
        )


if __name__ == "__main__":
    main()
