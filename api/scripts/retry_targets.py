"""Retry only missing carrier takes, then rebuild the Stage 0 audit from cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dau.content import inventory_document, word_surface
from dau.models import REFERENCE_MODEL
from dau.realtime_audio import voice_prompt
from dau.settings import TARGETS_ROOT
from dau.spend import approve
from scripts.gen_targets import (
    ESTIMATED_CANDIDATE_USD,
    TAKES_PER_WORD,
    _choose,
    _generate_candidate,
    _lexical_identity,
    _validate,
)


def _key(record: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        record["accent"],
        record["word_id"],
        record["source_mode"],
        int(record["take"]),
    )


def _candidate_record(
    word: dict[str, Any], accent: str, candidate: dict[str, Any]
) -> dict[str, Any]:
    return {
        "word_id": word["id"],
        "surface": word_surface(word),
        "tone": word["tone"],
        "accent": accent,
        **candidate,
    }


def _revalidate_with_receipt(record: dict[str, Any], word: dict[str, Any]) -> None:
    if record.get("sha256") is None:
        return
    path = TARGETS_ROOT.parent / record["path"]
    stored = record.get("validation", {})
    lexical = stored.get("lexical_verified")
    if isinstance(lexical, bool):
        validation = _validate(path, word, record["accent"], lexical_verified=lexical)
        validation["transcript"] = stored.get("transcript", "")
        validation["lexical_verified"] = lexical
        record["validation"] = validation
        return

    acoustic = _validate(path, word, record["accent"], lexical_verified=True)
    if not acoustic.get("passed"):
        acoustic["transcript"] = ""
        acoustic["lexical_verified"] = None
        record["validation"] = acoustic
        return
    lexical_verified, transcript = _lexical_identity(path, word)
    validation = _validate(
        path,
        word,
        record["accent"],
        lexical_verified=lexical_verified,
    )
    validation["transcript"] = transcript
    validation["lexical_verified"] = lexical_verified
    record["validation"] = validation


def _cached_record(path: Path, word: dict[str, Any], accent: str) -> dict[str, Any]:
    source_mode = path.parent.name
    take = int(path.stem.removeprefix("take-"))
    return _candidate_record(
        word,
        accent,
        {
            "take": take,
            "path": str(path.relative_to(TARGETS_ROOT.parent)),
            "source_mode": source_mode,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "validation": {},
        },
    )


def _selected_record(word: dict[str, Any], accent: str, choice: dict[str, Any]) -> dict[str, Any]:
    source = TARGETS_ROOT.parent / choice["path"]
    destination = TARGETS_ROOT / accent / f"{word['id']}.wav"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() != destination.resolve():
        destination.write_bytes(source.read_bytes())
    return {
        "word_id": word["id"],
        "surface": word_surface(word),
        "tone": word["tone"],
        "accent": accent,
        "model": REFERENCE_MODEL,
        "voice": "cedar",
        "voice_prompt": voice_prompt(accent),
        "source_mode": choice["source_mode"],
        "take": choice["take"],
        "path": str(destination.relative_to(TARGETS_ROOT.parent)),
        "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        "contour": choice["validation"].get("contour", []),
        "features": choice["validation"].get("features", {}),
        "validation": choice["validation"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pair",
        action="append",
        required=True,
        metavar="ACCENT/WORD_ID",
        help="Residual pair allowed to receive missing carrier takes.",
    )
    parser.add_argument("--workers", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()

    requested = set(args.pair)
    inventory = inventory_document().get("words", [])
    words = {word["id"]: word for word in inventory}
    expected_pairs = {
        f"{accent}/{word['id']}" for accent in ("north", "south") for word in inventory
    }
    unknown = sorted(requested - expected_pairs)
    if unknown:
        parser.error(f"unknown pairs: {', '.join(unknown)}")

    report_path = TARGETS_ROOT / "generation-report.json"
    previous = json.loads(report_path.read_text(encoding="utf-8"))
    records: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    for record in previous.get("rejected", []) + previous.get("targets", []):
        records[_key(record)] = record

    for pair in sorted(requested):
        accent, word_id = pair.split("/", 1)
        word = words[word_id]
        root = TARGETS_ROOT / "candidates" / accent / word_id
        for path in sorted(root.glob("*/take-*.wav")):
            if path.name.endswith(".raw.wav"):
                continue
            candidate = _cached_record(path, word, accent)
            key = _key(candidate)
            if key not in records or records[key].get("sha256") is None:
                records[key] = candidate

    for record in records.values():
        word = words[record["word_id"]]
        _revalidate_with_receipt(record, word)

    generation_jobs: list[tuple[dict[str, Any], str, int]] = []
    for pair in sorted(requested):
        accent, word_id = pair.split("/", 1)
        word = words[word_id]
        pair_records = [record for key, record in records.items() if key[:2] == (accent, word_id)]
        isolated = [record for record in pair_records if record["source_mode"] == "isolated"]
        carrier = [record for record in pair_records if record["source_mode"] == "carrier"]
        if _choose(isolated) is not None or _choose(carrier) is not None:
            continue
        existing_takes = {
            int(record["take"]) for record in carrier if record.get("sha256") is not None
        }
        generation_jobs.extend(
            (word, accent, take)
            for take in range(1, TAKES_PER_WORD + 1)
            if take not in existing_takes
        )

    approve(
        len(generation_jobs) * ESTIMATED_CANDIDATE_USD,
        f"residual carrier retry (maximum {len(generation_jobs)} calls)",
    )
    print(f"Retrying {len(generation_jobs)} missing carrier takes from {len(requested)} pairs")
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(_generate_candidate, word, accent, "carrier", take)
            for word, accent, take in generation_jobs
        ]
        for (word, accent, _take), future in zip(generation_jobs, futures, strict=True):
            candidate = _candidate_record(word, accent, future.result())
            records[_key(candidate)] = candidate

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for accent in ("north", "south"):
        for word in inventory:
            candidates = [
                record for key, record in records.items() if key[:2] == (accent, word["id"])
            ]
            choice = _choose(candidates)
            if choice is None:
                failures.append(
                    {
                        "pair_id": f"{accent}/{word['id']}",
                        "accent": accent,
                        "word_id": word["id"],
                        "surface": word_surface(word),
                        "tone": word["tone"],
                        "reason": "no_candidate_passed",
                    }
                )
            else:
                selected.append(_selected_record(word, accent, choice))
            rejected.extend(
                record for record in candidates if choice is None or _key(record) != _key(choice)
            )

    report = {
        "schema_version": 1,
        "status": "blocked" if failures else "validated",
        "model": REFERENCE_MODEL,
        "voice": "cedar",
        "candidate_takes_per_word_accent": TAKES_PER_WORD,
        "known_failed_pairs_skipped": [],
        "targets": selected,
        "rejected": rejected,
        "failures": failures,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if failures:
        print("No validated target for:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure['pair_id']} ({failure['surface']})", file=sys.stderr)
        raise SystemExit(2)

    manifest = {key: value for key, value in report.items() if key not in {"status", "failures"}}
    (TARGETS_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Validated all {len(selected)} targets")


if __name__ == "__main__":
    main()
