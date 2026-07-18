"""Build the committed no-microphone analyzer and Echo fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, cast

from dau.content import target_manifest
from dau.settings import DATA_ROOT, REPO_ROOT, TARGETS_ROOT
from dau.spend import approve
from scripts.gen_echo_audio import ESTIMATED_UTTERANCE_USD, _generate_validated

ANALYZER_SOURCES = {
    "ma-mother-correct": ("ma-mother", "south"),
    "ma-mother-said-ghost": ("ma-ghost", "south"),
    "phuong-name-said-ward": ("phuong-ward", "north"),
}
WRONG_ECHO_TEXT = "Tối nay con mời ma đi ăn cơm."


def _validated_source(word_id: str, accent: str) -> Path:
    targets = target_manifest().get("targets", [])
    if not targets:
        report_path = TARGETS_ROOT / "generation-report.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            targets = report.get("targets", [])
    target = next(
        (
            item
            for item in targets
            if item.get("word_id") == word_id and item.get("accent") == accent
        ),
        None,
    )
    if not target or not target.get("validation", {}).get("passed"):
        raise RuntimeError(f"Missing validated source target: {accent}/{word_id}")
    source = REPO_ROOT / cast(str, target["path"])
    if not source.is_file():
        raise RuntimeError(f"Validated source file is absent: {source}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != target.get("sha256"):
        raise RuntimeError(f"Validated source hash does not match its receipt: {source}")
    return source


def _stamp(entries: list[dict[str, Any]]) -> None:
    for entry in entries:
        path = REPO_ROOT / entry["recording_path"]
        if not path.is_file():
            raise RuntimeError(f"Fixture was not produced: {path}")
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    manifest_path = DATA_ROOT / "demo_manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    analyzer_entries = document.get("analyzer_demos", [])
    for entry in analyzer_entries:
        word_id, accent = ANALYZER_SOURCES[entry["id"]]
        destination = REPO_ROOT / entry["recording_path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_validated_source(word_id, accent), destination)

    echo_entry = document["echo_demos"][0]
    echo_path = REPO_ROOT / echo_entry["recording_path"]
    echo_path.parent.mkdir(parents=True, exist_ok=True)
    if not echo_path.exists():
        approve(
            ESTIMATED_UTTERANCE_USD * 2,
            "wrong-tone Echo demo with full-model fallback allowance",
        )
        model, validation = _generate_validated(WRONG_ECHO_TEXT, "south", echo_path)
        echo_entry["generation"] = {
            "model": model,
            "voice": "cedar",
            "validation": validation,
        }

    _stamp(analyzer_entries)
    _stamp(document.get("echo_demos", []))
    manifest_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"generated {len(analyzer_entries)} analyzer fixtures and one Echo fixture")
    print(f"assets live under {TARGETS_ROOT / 'demos'}")


if __name__ == "__main__":
    main()
