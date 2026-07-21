from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from dau.content import inventory_document
from scripts import import_phone_targets


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pair_order() -> list[tuple[str, dict[str, Any]]]:
    words = inventory_document()["words"]
    return [(accent, word) for accent in ("north", "south") for word in words]


def _write_blocked_report(
    repo_root: Path,
    *,
    failed_pairs: set[str],
    corrupt_pair: str | None = None,
) -> Path:
    targets_root = repo_root / "targets"
    targets: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for accent, word in _pair_order():
        pair_id = f"{accent}/{word['id']}"
        if pair_id in failed_pairs:
            failures.append(
                {
                    "pair_id": pair_id,
                    "accent": accent,
                    "word_id": word["id"],
                    "surface": word["syllable"],
                    "tone": word["tone"],
                    "reason": "no_candidate_passed",
                }
            )
            continue
        path = targets_root / accent / f"{word['id']}.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"validated:{pair_id}".encode()
        path.write_bytes(data)
        targets.append(
            {
                "word_id": word["id"],
                "surface": word["syllable"],
                "tone": word["tone"],
                "accent": accent,
                "model": "gpt-realtime-2.1",
                "voice": "cedar",
                "source_mode": "isolated",
                "path": str(path.relative_to(repo_root)),
                "sha256": "0" * 64 if pair_id == corrupt_pair else _hash(data),
                "contour": [0.0] * 64,
                "features": {},
                "validation": {"passed": True, "lexical_verified": True},
            }
        )
    report = {
        "schema_version": 1,
        "status": "blocked",
        "model": "gpt-realtime-2.1",
        "voice": "cedar",
        "candidate_takes_per_word_accent": 5,
        "targets": targets,
        "rejected": [],
        "failures": failures,
    }
    report_path = targets_root / "generation-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report_path


def _patch_audio_and_validation(monkeypatch, *, rejected_accent: str | None = None) -> None:
    sample_rate = 44_100
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    waveform = 0.18 * np.sin(2 * np.pi * 190 * time)
    monkeypatch.setattr(
        import_phone_targets,
        "decode_audio",
        lambda _source: (waveform.copy(), sample_rate),
    )

    def lexical(path: Path, word: dict[str, Any]) -> tuple[bool, str]:
        matched = rejected_accent is None or f"-{rejected_accent}-" not in path.name
        return matched, word["syllable"] if matched else "sai"

    def validate(
        _path: Path,
        expected_tone: str,
        *,
        accent: str,
        lexical_verified: bool,
    ) -> dict[str, Any]:
        del expected_tone, accent
        return {
            "passed": lexical_verified,
            "reason_codes": [] if lexical_verified else ["lexical_mismatch"],
            "contour": [0.0] * 64,
            "features": {"slope": 0.0},
            "quality": {"active_duration_s": 0.5},
        }

    monkeypatch.setattr(import_phone_targets, "_lexical_identity", lexical)
    monkeypatch.setattr(import_phone_targets, "validate_target_candidate", validate)


def _phone_file(path: Path, content: bytes = b"phone-container") -> Path:
    path.write_bytes(content)
    return path


def test_phone_audio_is_normalized_to_mono_22050_pcm16(monkeypatch, tmp_path) -> None:
    _patch_audio_and_validation(monkeypatch)
    source = _phone_file(tmp_path / "recording.m4a")
    destination = tmp_path / "normalized.wav"

    import_phone_targets._normalize_phone_audio(source, destination)

    info = sf.info(destination)
    assert info.samplerate == 22_050
    assert info.channels == 1
    assert info.subtype == "PCM_16"


def test_one_failed_recording_prevents_every_supplied_mutation(monkeypatch, tmp_path) -> None:
    failed_pairs = {"north/ma-grave", "south/ma-grave"}
    report_path = _write_blocked_report(tmp_path, failed_pairs=failed_pairs)
    report_before = report_path.read_bytes()
    north_destination = tmp_path / "targets/north/ma-grave.wav"
    south_destination = tmp_path / "targets/south/ma-grave.wav"
    north_phone = _phone_file(tmp_path / "north.m4a", b"north-phone")
    south_phone = _phone_file(tmp_path / "south.m4a", b"south-phone")
    _patch_audio_and_validation(monkeypatch, rejected_accent="south")

    try:
        import_phone_targets.import_recordings(
            [
                f"north/ma-grave={north_phone}",
                f"south/ma-grave={south_phone}",
            ],
            targets_root=tmp_path / "targets",
            inventory=inventory_document(),
        )
    except import_phone_targets.PhoneImportError as error:
        assert "lexical_mismatch" in str(error)
    else:
        raise AssertionError("failed phone recording was promoted")

    assert report_path.read_bytes() == report_before
    assert not north_destination.exists()
    assert not south_destination.exists()
    assert not (tmp_path / "targets/manifest.json").exists()


def test_passing_partial_import_replaces_only_its_failure(monkeypatch, tmp_path) -> None:
    _write_blocked_report(
        tmp_path,
        failed_pairs={"north/ma-grave", "south/ma-grave"},
    )
    phone = _phone_file(tmp_path / "north-ma-grave.caf")
    _patch_audio_and_validation(monkeypatch)

    result = import_phone_targets.import_recordings(
        [f"north/ma-grave={phone}"],
        targets_root=tmp_path / "targets",
        inventory=inventory_document(),
    )

    report = json.loads((tmp_path / "targets/generation-report.json").read_text())
    imported = next(
        target
        for target in report["targets"]
        if target["accent"] == "north" and target["word_id"] == "ma-grave"
    )
    assert result.manifest_written is False
    assert result.remaining_failures == ("south/ma-grave",)
    assert report["status"] == "blocked"
    assert [failure["pair_id"] for failure in report["failures"]] == ["south/ma-grave"]
    assert imported["source_mode"] == "phone_recording"
    assert imported["provenance"]["kind"] == "user_supplied_phone_recording"
    assert imported["source_sha256"] == _hash(phone.read_bytes())
    normalized = tmp_path / imported["path"]
    assert imported["sha256"] == _hash(normalized.read_bytes())
    assert not (tmp_path / "targets/manifest.json").exists()


def test_native_speaker_contrast_can_verify_an_asr_ambiguous_tone(
    monkeypatch, tmp_path
) -> None:
    _write_blocked_report(tmp_path, failed_pairs={"north/ma-grave", "south/ma-grave"})
    target_phone = _phone_file(tmp_path / "ma-grave.m4a", b"native-hoi")
    contrast_phone = _phone_file(tmp_path / "ma-code.m4a", b"native-nga")
    _patch_audio_and_validation(monkeypatch)

    def contrast_aware_lexical(path: Path, word: dict[str, Any]) -> tuple[bool, str]:
        if "contrast-ma-code" in path.name:
            return True, "mã"
        return False, "mã"

    monkeypatch.setattr(import_phone_targets, "_lexical_identity", contrast_aware_lexical)

    result = import_phone_targets.import_recordings(
        [f"north/ma-grave={target_phone}"],
        raw_contrast_specs=[f"north/ma-grave=ma-code={contrast_phone}"],
        targets_root=tmp_path / "targets",
        inventory=inventory_document(),
    )

    report = json.loads((tmp_path / "targets/generation-report.json").read_text())
    imported = next(
        target
        for target in report["targets"]
        if target["accent"] == "north" and target["word_id"] == "ma-grave"
    )
    lexical = imported["provenance"]["lexical_validation"]
    evidence = tmp_path / lexical["contrast_path"]
    assert result.manifest_written is False
    assert imported["validation"]["lexical_verified"] is True
    assert imported["validation"]["transcript"] == "mã"
    assert lexical["method"] == "native_speaker_labeled_minimal_pair"
    assert lexical["target_asr_exact"] is False
    assert lexical["contrast_word_id"] == "ma-code"
    assert evidence.is_file()
    assert lexical["contrast_sha256"] == _hash(evidence.read_bytes())


def test_manifest_is_written_only_when_all_38_targets_are_hash_valid(monkeypatch, tmp_path) -> None:
    _write_blocked_report(tmp_path, failed_pairs={"south/phuong-phoenix"})
    phone = _phone_file(tmp_path / "phoenix.mov")
    _patch_audio_and_validation(monkeypatch)

    result = import_phone_targets.import_recordings(
        [f"south/phuong-phoenix={phone}"],
        targets_root=tmp_path / "targets",
        inventory=inventory_document(),
    )

    report = json.loads((tmp_path / "targets/generation-report.json").read_text())
    manifest = json.loads((tmp_path / "targets/manifest.json").read_text())
    assert result.manifest_written is True
    assert report["status"] == "validated"
    assert report["failures"] == []
    assert report["integrity_errors"] == []
    assert len(manifest["targets"]) == 38
    assert all(target["validation"]["passed"] for target in manifest["targets"])
    for target in manifest["targets"]:
        path = tmp_path / target["path"]
        assert target["sha256"] == _hash(path.read_bytes())


def test_bad_existing_hash_keeps_manifest_blocked(monkeypatch, tmp_path) -> None:
    _write_blocked_report(
        tmp_path,
        failed_pairs={"south/phuong-phoenix"},
        corrupt_pair="north/ma-ghost",
    )
    phone = _phone_file(tmp_path / "phoenix.webm")
    _patch_audio_and_validation(monkeypatch)

    result = import_phone_targets.import_recordings(
        [f"south/phuong-phoenix={phone}"],
        targets_root=tmp_path / "targets",
        inventory=inventory_document(),
    )

    report = json.loads((tmp_path / "targets/generation-report.json").read_text())
    assert result.manifest_written is False
    assert report["status"] == "blocked"
    assert "hash_mismatch:north/ma-ghost" in report["integrity_errors"]
    assert not (tmp_path / "targets/manifest.json").exists()


def test_validated_target_cannot_be_replaced_while_another_pair_is_blocked(
    monkeypatch, tmp_path
) -> None:
    report_path = _write_blocked_report(tmp_path, failed_pairs={"south/phuong-phoenix"})
    report_before = report_path.read_bytes()
    target_path = tmp_path / "targets/north/ma-ghost.wav"
    target_before = target_path.read_bytes()
    phone = _phone_file(tmp_path / "replacement.m4a")
    _patch_audio_and_validation(monkeypatch)

    try:
        import_phone_targets.import_recordings(
            [f"north/ma-ghost={phone}"],
            targets_root=tmp_path / "targets",
            inventory=inventory_document(),
        )
    except import_phone_targets.PhoneImportError as error:
        assert "blocked failure or audited integrity error" in str(error)
    else:
        raise AssertionError("validated target was replaced without an integrity defect")

    assert report_path.read_bytes() == report_before
    assert target_path.read_bytes() == target_before


def test_report_metadata_must_match_inventory_before_validation(monkeypatch, tmp_path) -> None:
    report_path = _write_blocked_report(tmp_path, failed_pairs={"south/phuong-phoenix"})
    report = json.loads(report_path.read_text())
    report["failures"][0]["tone"] = "ngang"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    phone = _phone_file(tmp_path / "phoenix.m4a")
    _patch_audio_and_validation(monkeypatch)

    try:
        import_phone_targets.import_recordings(
            [f"south/phuong-phoenix={phone}"],
            targets_root=tmp_path / "targets",
            inventory=inventory_document(),
        )
    except import_phone_targets.PhoneImportError as error:
        assert "metadata does not match the inventory" in str(error)
    else:
        raise AssertionError("mismatched report metadata reached phone validation")


def test_transaction_rolls_back_files_when_a_later_write_fails(monkeypatch, tmp_path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b"before")
    original_atomic_write = import_phone_targets._atomic_write
    failure_injected = False

    def fail_second_once(path: Path, data: bytes) -> None:
        nonlocal failure_injected
        if path == second and not failure_injected:
            failure_injected = True
            raise OSError("simulated write failure")
        original_atomic_write(path, data)

    monkeypatch.setattr(import_phone_targets, "_atomic_write", fail_second_once)

    try:
        import_phone_targets._apply_transaction(
            {first: b"after", second: b"new"}
        )
    except import_phone_targets.PhoneImportError as error:
        assert "rolled back" in str(error)
    else:
        raise AssertionError("transaction failure was not surfaced")

    assert first.read_bytes() == b"before"
    assert not second.exists()
