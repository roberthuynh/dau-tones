"""Import phone recordings only after lexical, signal, and tone validation pass.

Usage::

    uv run --directory api python -m scripts.import_phone_targets \
        north/ma-grave=/path/to/north-ma-grave.m4a \
        south/ma-grave=/path/to/south-ma-grave.m4a

The importer is deliberately transactional. It normalizes and validates every
supplied recording in a temporary directory before changing the target corpus.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]
from scipy.signal import resample_poly  # type: ignore[import-untyped]

from dau.content import clear_content_caches, inventory_document, word_surface
from dau.settings import TARGETS_ROOT
from dau.tones import SAMPLE_RATE, decode_audio, validate_target_candidate

from .gen_targets import _lexical_identity

EXPECTED_ACCENTS = ("north", "south")
EXPECTED_TARGET_COUNT = 38


class PhoneImportError(RuntimeError):
    """A safe importer rejection that leaves the committed corpus untouched."""


@dataclass(frozen=True)
class ImportSpec:
    accent: str
    word_id: str
    source_path: Path

    @property
    def pair_id(self) -> str:
        return f"{self.accent}/{self.word_id}"


@dataclass(frozen=True)
class ImportResult:
    imported_pairs: tuple[str, ...]
    remaining_failures: tuple[str, ...]
    manifest_written: bool


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PhoneImportError(f"Required Stage 0 report is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise PhoneImportError(f"Stage 0 report is not valid JSON: {path}") from error
    if not isinstance(value, dict):
        raise PhoneImportError(f"Stage 0 report must contain a JSON object: {path}")
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _parse_specs(
    raw_specs: Sequence[str], words_by_id: Mapping[str, dict[str, Any]]
) -> list[ImportSpec]:
    if not raw_specs:
        raise PhoneImportError("Provide at least one ACCENT/WORD_ID=PATH recording.")
    parsed: list[ImportSpec] = []
    seen: set[str] = set()
    for raw_spec in raw_specs:
        pair, separator, raw_path = raw_spec.partition("=")
        accent, slash, word_id = pair.partition("/")
        if not separator or not slash or not accent or not word_id or not raw_path:
            raise PhoneImportError(
                f"Invalid recording spec {raw_spec!r}; expected ACCENT/WORD_ID=PATH."
            )
        if accent not in EXPECTED_ACCENTS:
            raise PhoneImportError(f"Unknown accent {accent!r} in {raw_spec!r}.")
        if word_id not in words_by_id:
            raise PhoneImportError(f"Unknown inventory word ID {word_id!r} in {raw_spec!r}.")
        pair_id = f"{accent}/{word_id}"
        if pair_id in seen:
            raise PhoneImportError(f"Duplicate recording spec for {pair_id}.")
        source_path = Path(raw_path).expanduser().resolve()
        if not source_path.is_file():
            raise PhoneImportError(
                f"Phone recording does not exist or is not a file: {source_path}"
            )
        seen.add(pair_id)
        parsed.append(ImportSpec(accent=accent, word_id=word_id, source_path=source_path))
    return parsed


def _normalize_phone_audio(source: Path, destination: Path) -> None:
    """Use the shared PyAV decoder, then emit mono 22.05 kHz PCM16 WAV."""

    samples, sample_rate = decode_audio(source)
    waveform = np.asarray(samples, dtype=np.float32).reshape(-1)
    if not waveform.size or not np.all(np.isfinite(waveform)):
        raise PhoneImportError(f"Decoded phone recording is empty or non-finite: {source}")
    if sample_rate <= 0:
        raise PhoneImportError(f"Decoded phone recording has an invalid sample rate: {source}")
    if sample_rate != SAMPLE_RATE:
        divisor = math.gcd(int(sample_rate), SAMPLE_RATE)
        waveform = np.asarray(
            resample_poly(waveform, SAMPLE_RATE // divisor, int(sample_rate) // divisor),
            dtype=np.float32,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destination, waveform, SAMPLE_RATE, subtype="PCM_16", format="WAV")


def _validation_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if not isinstance(value, Mapping):
        raise PhoneImportError("DSP target validator returned an invalid result.")
    return dict(value)


def _safe_target_path(relative_path: Any, repo_root: Path) -> Path | None:
    if not isinstance(relative_path, str):
        return None
    candidate = Path(relative_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved = (repo_root / candidate).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return None
    return resolved


def _audit_targets(
    targets: Sequence[Mapping[str, Any]],
    *,
    expected_pairs: set[tuple[str, str]],
    repo_root: Path,
    pending_files: Mapping[Path, bytes],
) -> list[str]:
    errors: list[str] = []
    if len(expected_pairs) != EXPECTED_TARGET_COUNT:
        errors.append(
            f"inventory_expected_{EXPECTED_TARGET_COUNT}_pairs_found_{len(expected_pairs)}"
        )
    seen: set[tuple[str, str]] = set()
    for target in targets:
        key = (str(target.get("accent", "")), str(target.get("word_id", "")))
        pair_id = f"{key[0]}/{key[1]}"
        if key not in expected_pairs:
            errors.append(f"unexpected_pair:{pair_id}")
            continue
        if key in seen:
            errors.append(f"duplicate_pair:{pair_id}")
            continue
        seen.add(key)
        validation = target.get("validation")
        if not isinstance(validation, Mapping) or validation.get("passed") is not True:
            errors.append(f"validation_not_passed:{pair_id}")
        elif validation.get("lexical_verified") is not True:
            errors.append(f"lexical_not_verified:{pair_id}")
        path = _safe_target_path(target.get("path"), repo_root)
        if path is None:
            errors.append(f"unsafe_path:{pair_id}")
            continue
        expected_path = repo_root / "targets" / key[0] / f"{key[1]}.wav"
        if path != expected_path.resolve():
            errors.append(f"unexpected_path:{pair_id}")
            continue
        data = pending_files.get(path)
        if data is None:
            try:
                data = path.read_bytes()
            except OSError:
                errors.append(f"missing_file:{pair_id}")
                continue
        digest = target.get("sha256")
        if not isinstance(digest, str) or _sha256(data) != digest:
            errors.append(f"hash_mismatch:{pair_id}")
    for accent, word_id in sorted(expected_pairs - seen):
        errors.append(f"missing_pair:{accent}/{word_id}")
    return errors


def _validate_report_inventory(
    targets: Sequence[Any],
    failures: Sequence[Any],
    *,
    words_by_id: Mapping[str, dict[str, Any]],
    expected_pairs: set[tuple[str, str]],
) -> set[str]:
    """Require the blocked report to describe the current inventory exactly once."""

    target_pairs: set[tuple[str, str]] = set()
    failure_pairs: set[tuple[str, str]] = set()

    def checked_pair(record: Any, *, kind: str) -> tuple[str, str]:
        if not isinstance(record, Mapping):
            raise PhoneImportError(f"Stage 0 report {kind} entries must be objects.")
        accent = record.get("accent")
        word_id = record.get("word_id")
        if not isinstance(accent, str) or not isinstance(word_id, str):
            raise PhoneImportError(
                f"Stage 0 report {kind} entries require string accent and word_id fields."
            )
        pair = (accent, word_id)
        pair_id = f"{accent}/{word_id}"
        if pair not in expected_pairs:
            raise PhoneImportError(
                f"Stage 0 report {kind} entry is not in the inventory: {pair_id}."
            )
        word = words_by_id[word_id]
        if record.get("surface") != word_surface(word) or record.get("tone") != word.get("tone"):
            raise PhoneImportError(
                f"Stage 0 report metadata does not match the inventory for {pair_id}."
            )
        if kind == "failure" and record.get("pair_id") != pair_id:
            raise PhoneImportError(
                f"Stage 0 failure pair_id does not match its accent and word_id: {pair_id}."
            )
        return pair

    for target in targets:
        pair = checked_pair(target, kind="target")
        if pair in target_pairs:
            raise PhoneImportError(f"Duplicate Stage 0 target: {pair[0]}/{pair[1]}.")
        target_pairs.add(pair)
    for failure in failures:
        pair = checked_pair(failure, kind="failure")
        if pair in failure_pairs:
            raise PhoneImportError(f"Duplicate Stage 0 failure: {pair[0]}/{pair[1]}.")
        if pair in target_pairs:
            raise PhoneImportError(
                f"Stage 0 pair is both validated and failed: {pair[0]}/{pair[1]}."
            )
        failure_pairs.add(pair)

    described_pairs = target_pairs | failure_pairs
    if described_pairs != expected_pairs:
        missing = sorted(
            f"{accent}/{word_id}" for accent, word_id in expected_pairs - described_pairs
        )
        raise PhoneImportError(
            "Stage 0 report does not cover the inventory exactly; missing: "
            + (", ".join(missing) or "none")
        )
    return {f"{accent}/{word_id}" for accent, word_id in failure_pairs}


def _integrity_error_pairs(errors: Sequence[str], expected_pairs: set[tuple[str, str]]) -> set[str]:
    expected_ids = {f"{accent}/{word_id}" for accent, word_id in expected_pairs}
    pair_ids: set[str] = set()
    for error in errors:
        _, separator, pair_id = error.partition(":")
        if separator and pair_id in expected_ids:
            pair_ids.add(pair_id)
    return pair_ids


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _apply_transaction(writes: Mapping[Path, bytes]) -> None:
    snapshots: dict[Path, bytes | None] = {}
    completed: list[Path] = []
    try:
        for path, data in writes.items():
            snapshots[path] = path.read_bytes() if path.exists() else None
            _atomic_write(path, data)
            completed.append(path)
    except Exception as error:
        rollback_errors: list[str] = []
        for path in reversed(completed):
            previous = snapshots[path]
            try:
                if previous is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write(path, previous)
            except OSError as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        detail = f" Rollback errors: {'; '.join(rollback_errors)}" if rollback_errors else ""
        raise PhoneImportError(
            f"Phone import transaction failed and was rolled back.{detail}"
        ) from error


def import_recordings(
    raw_specs: Sequence[str],
    *,
    targets_root: Path | None = None,
    inventory: Mapping[str, Any] | None = None,
    imported_at: datetime | None = None,
) -> ImportResult:
    """Validate all supplied recordings, then atomically update the blocked corpus."""

    resolved_targets_root = (targets_root or TARGETS_ROOT).resolve()
    repo_root = resolved_targets_root.parent
    document = dict(inventory or inventory_document())
    words = document.get("words", [])
    if not isinstance(words, list):
        raise PhoneImportError("Inventory words must be a list.")
    if not all(
        isinstance(word, dict) and isinstance(word.get("id"), str) for word in words
    ):
        raise PhoneImportError("Every inventory word must be an object with a string ID.")
    words_by_id = {
        str(word["id"]): word
        for word in words
        if isinstance(word, dict) and isinstance(word.get("id"), str)
    }
    if len(words_by_id) != len(words):
        raise PhoneImportError("Inventory word IDs must be unique.")
    expected_pairs = {
        (accent, word_id) for accent in EXPECTED_ACCENTS for word_id in words_by_id
    }
    if len(expected_pairs) != EXPECTED_TARGET_COUNT:
        raise PhoneImportError(
            f"Inventory must resolve to exactly {EXPECTED_TARGET_COUNT} accent/word pairs; "
            f"found {len(expected_pairs)}."
        )
    specs = _parse_specs(raw_specs, words_by_id)
    report_path = resolved_targets_root / "generation-report.json"
    manifest_path = resolved_targets_root / "manifest.json"
    report = _load_json(report_path)
    if report.get("status") != "blocked":
        raise PhoneImportError("Phone fallback imports require a blocked Stage 0 report.")
    report_targets = report.get("targets", [])
    report_failures = report.get("failures", [])
    if not isinstance(report_targets, list) or not isinstance(report_failures, list):
        raise PhoneImportError("Stage 0 report targets and failures must be lists.")
    failure_pair_ids = _validate_report_inventory(
        report_targets,
        report_failures,
        words_by_id=words_by_id,
        expected_pairs=expected_pairs,
    )
    existing_integrity_errors = _audit_targets(
        report_targets,
        expected_pairs=expected_pairs,
        repo_root=repo_root,
        pending_files={},
    )
    repairable_pair_ids = failure_pair_ids | _integrity_error_pairs(
        existing_integrity_errors, expected_pairs
    )
    unmatched = [spec.pair_id for spec in specs if spec.pair_id not in repairable_pair_ids]
    if unmatched:
        raise PhoneImportError(
            "Recordings do not match a blocked failure or audited integrity error: "
            + ", ".join(unmatched)
        )

    timestamp = (imported_at or datetime.now(UTC)).astimezone(UTC).isoformat()
    staged_records: list[dict[str, Any]] = []
    staged_files: dict[Path, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="dau-phone-import-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        for index, spec in enumerate(specs):
            word = words_by_id[spec.word_id]
            normalized_path = temporary_root / f"{index}-{spec.accent}-{spec.word_id}.wav"
            try:
                source_bytes = spec.source_path.read_bytes()
                _normalize_phone_audio(spec.source_path, normalized_path)
                lexical_verified, transcript = _lexical_identity(normalized_path, word)
                validation = _validation_dict(
                    validate_target_candidate(
                        normalized_path,
                        expected_tone=word["tone"],
                        accent=spec.accent,
                        lexical_verified=lexical_verified,
                    )
                )
            except PhoneImportError:
                raise
            except Exception as error:
                raise PhoneImportError(f"Validation failed for {spec.pair_id}: {error}") from error
            validation["transcript"] = transcript
            validation["lexical_verified"] = bool(lexical_verified)
            if not lexical_verified:
                validation["passed"] = False
                reasons = list(validation.get("reason_codes", []))
                if "lexical_mismatch" not in reasons:
                    reasons.append("lexical_mismatch")
                validation["reason_codes"] = reasons
            if validation.get("passed") is not True:
                reason_text = ", ".join(
                    str(reason) for reason in validation.get("reason_codes", [])
                )
                raise PhoneImportError(
                    f"Recording {spec.pair_id} failed validation"
                    + (f": {reason_text}" if reason_text else ".")
                )
            normalized_bytes = normalized_path.read_bytes()
            destination = resolved_targets_root / spec.accent / f"{spec.word_id}.wav"
            normalized_hash = _sha256(normalized_bytes)
            provenance = {
                "kind": "user_supplied_phone_recording",
                "imported_at": timestamp,
                "source_filename": spec.source_path.name,
                "source_sha256": _sha256(source_bytes),
                "normalized_sha256": normalized_hash,
                "normalized_format": {
                    "container": "wav",
                    "codec": "pcm_s16le",
                    "channels": 1,
                    "sample_rate_hz": SAMPLE_RATE,
                },
            }
            staged_records.append(
                {
                    "word_id": spec.word_id,
                    "surface": word_surface(word),
                    "tone": word["tone"],
                    "accent": spec.accent,
                    "model": None,
                    "voice": "user",
                    "voice_prompt": None,
                    "source_mode": "phone_recording",
                    "take": None,
                    "path": str(destination.relative_to(repo_root)),
                    "sha256": normalized_hash,
                    "source_sha256": provenance["source_sha256"],
                    "contour": validation.get("contour", []),
                    "features": validation.get("features", {}),
                    "validation": validation,
                    "provenance": provenance,
                }
            )
            staged_files[destination.resolve()] = normalized_bytes

    imported_pair_ids = {spec.pair_id for spec in specs}
    imported_keys = {(spec.accent, spec.word_id) for spec in specs}
    planned_targets = [
        dict(target)
        for target in report_targets
        if isinstance(target, Mapping)
        and (str(target.get("accent")), str(target.get("word_id"))) not in imported_keys
    ]
    planned_targets.extend(staged_records)
    word_order = {word_id: index for index, word_id in enumerate(words_by_id)}
    accent_order = {accent: index for index, accent in enumerate(EXPECTED_ACCENTS)}
    planned_targets.sort(
        key=lambda target: (
            accent_order.get(str(target.get("accent")), len(accent_order)),
            word_order.get(str(target.get("word_id")), len(word_order)),
        )
    )
    planned_failures = [
        dict(failure)
        for failure in report_failures
        if isinstance(failure, Mapping) and str(failure.get("pair_id")) not in imported_pair_ids
    ]
    integrity_errors = _audit_targets(
        planned_targets,
        expected_pairs=expected_pairs,
        repo_root=repo_root,
        pending_files=staged_files,
    )
    corpus_complete = not planned_failures and not integrity_errors
    planned_report = dict(report)
    planned_report["status"] = "validated" if corpus_complete else "blocked"
    planned_report["targets"] = planned_targets
    planned_report["failures"] = planned_failures
    planned_report["integrity_errors"] = integrity_errors
    import_log = list(report.get("phone_imports", []))
    import_log.extend(
        {
            "pair_id": f"{record['accent']}/{record['word_id']}",
            **record["provenance"],
        }
        for record in staged_records
    )
    planned_report["phone_imports"] = import_log

    if manifest_path.exists() and not corpus_complete:
        raise PhoneImportError(
            "An existing manifest would become stale, so no files were changed. "
            "Repair every corpus integrity error in one import."
        )

    writes: dict[Path, bytes] = dict(staged_files)
    writes[report_path] = _json_bytes(planned_report)
    if corpus_complete:
        manifest = {
            "schema_version": report.get("schema_version", 1),
            "model": report.get("model"),
            "voice": report.get("voice"),
            "candidate_takes_per_word_accent": report.get("candidate_takes_per_word_accent"),
            "targets": planned_targets,
            "rejected": report.get("rejected", []),
            "phone_imports": import_log,
        }
        writes[manifest_path] = _json_bytes(manifest)
    _apply_transaction(writes)
    clear_content_caches()
    return ImportResult(
        imported_pairs=tuple(spec.pair_id for spec in specs),
        remaining_failures=tuple(
            str(failure.get("pair_id")) for failure in planned_failures
        ),
        manifest_written=corpus_complete,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Strictly validate phone recordings before replacing blocked Stage 0 targets."
    )
    parser.add_argument(
        "recording",
        nargs="+",
        metavar="ACCENT/WORD_ID=PATH",
        help="Repeat once per phone recording to import.",
    )
    args = parser.parse_args()
    try:
        result = import_recordings(args.recording)
    except PhoneImportError as error:
        parser.exit(2, f"phone target import rejected: {error}\n")
    print(f"validated and imported {len(result.imported_pairs)} phone target(s)")
    if result.manifest_written:
        print(
            f"complete {EXPECTED_TARGET_COUNT}-target manifest written to "
            f"{TARGETS_ROOT / 'manifest.json'}"
        )
    else:
        remaining = ", ".join(result.remaining_failures)
        print(
            "corpus remains blocked; remaining failures: "
            + (remaining or "see integrity_errors in generation-report.json")
        )


if __name__ == "__main__":
    main()
