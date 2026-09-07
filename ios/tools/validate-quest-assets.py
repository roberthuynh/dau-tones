#!/usr/bin/env python3
"""Deterministic, offline integrity checks for the VietQuest launch assets.

This verifies files and metadata only.  It cannot establish intelligibility,
speaker identity, accent, or dialect quality; those require a human listener.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


IDS = [f"C{i:02d}" for i in range(1, 9)]
GENERATED = {"C04", "C06", "C07", "C08"}
REUSED = {"C01", "C02", "C03", "C05"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def add(receipt: dict, name: str, passed: bool, detail: object) -> None:
    receipt["checks"][name] = {"passed": passed, "detail": detail}
    if not passed:
        receipt["passed"] = False


def swift_lines(path: Path) -> dict[str, str]:
    source = path.read_text(encoding="utf-8")
    pattern = re.compile(r'\.init\(id: "(C\d{2})", speaker: .*? vietnamese: "((?:\\.|[^"\\])*)"', re.S)
    return {ident: text.replace(r'\\"', '"').replace(r'\\\\', '\\') for ident, text in pattern.findall(source)}


def audio_signal(path: Path) -> dict:
    probe = json.loads(command("ffprobe", "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels,duration", "-show_entries", "format=duration", "-of", "json", str(path)))
    streams = probe.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"expected one audio stream, got {len(streams)}")
    stream = streams[0]
    duration = float(stream.get("duration") or probe["format"]["duration"])
    # silencedetect identifies long fully quiet runs; astats catches normalized clipping.
    process = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "silencedetect=noise=-60dB:d=1.0,astats=metadata=1:reset=0", "-f", "null", "-"],
        text=True, capture_output=True, check=True,
    )
    output = process.stderr
    silences = [float(value) for value in re.findall(r"silence_duration: ([0-9.]+)", output)]
    peaks = [float(value) for value in re.findall(r"Peak level dB: (-?(?:[0-9.]+|inf))", output)]
    peak = peaks[-1] if peaks else None
    return {
        "codec": stream.get("codec_name"), "sample_rate": int(stream["sample_rate"]),
        "channels": stream["channels"], "duration_seconds": round(duration, 6),
        "long_silence_seconds": silences, "peak_db": peak,
        "decodes": duration > 0, "no_long_silence": not silences,
        "not_clipped": peak is not None and peak < -0.1,
    }


def image_properties(path: Path) -> dict:
    output = command("sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "hasAlpha", str(path))
    fields = dict(re.findall(r"\s+(pixelWidth|pixelHeight|hasAlpha):\s*(\S+)", output))
    return {"width": int(fields["pixelWidth"]), "height": int(fields["pixelHeight"]), "has_alpha": fields["hasAlpha"] == "yes"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--write-receipt", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    art = root / "art/Generation/vietquest-v1"
    runtime = root / "ios/Resources/Content/quest/audio"
    receipt = {"schema": "vietquest-asset-validation/v1", "passed": True, "scope": "offline deterministic file, metadata, decode, and signal checks", "limitations": ["No listening review was performed.", "No accent, dialect, speaker-identity, intelligibility, or semantic-audio assurance is claimed."], "checks": {}}

    try:
        reuse = json.loads((art / "audio-reuse.json").read_text())
        generated_lines = json.loads((art / "audio-lines.json").read_text())
        lines = swift_lines(root / "ios/DauCore/Sources/DauCore/Quest/CafeQuest.swift")
        add(receipt, "swift_inventory", list(lines) == IDS, {"actual": list(lines), "expected": IDS})
        add(receipt, "runtime_inventory", sorted(p.stem for p in runtime.glob("C*.caf")) == IDS, {"actual": sorted(p.stem for p in runtime.glob("C*.caf")), "expected": IDS})

        reuse_by_id = {entry["episode_line"]: entry for entry in reuse}
        add(receipt, "reuse_manifest_inventory", set(reuse_by_id) == REUSED, {"actual": sorted(reuse_by_id), "expected": sorted(REUSED)})
        source_hashes = {}
        for ident in sorted(REUSED):
            entry = reuse_by_id.get(ident, {})
            file = root / entry.get("runtime_path", "")
            actual = sha256(file) if file.is_file() else None
            matched = actual == entry.get("sha256") and file.stat().st_size == entry.get("bytes") and lines.get(ident) == entry.get("transcript")
            source_hashes[ident] = {"runtime_path": str(file.relative_to(root)) if file.exists() else entry.get("runtime_path"), "expected_sha256": entry.get("sha256"), "actual_sha256": actual, "expected_bytes": entry.get("bytes"), "actual_bytes": file.stat().st_size if file.exists() else None, "transcript_matches_swift": lines.get(ident) == entry.get("transcript")}
            add(receipt, f"reuse_{ident}", matched, source_hashes[ident])
        receipt["source_hashes"] = source_hashes

        generated_by_id = {entry["id"]: entry for entry in generated_lines}
        add(receipt, "generated_manifest_inventory", set(generated_by_id) == GENERATED, {"actual": sorted(generated_by_id), "expected": sorted(GENERATED)})
        generated_receipts = {}
        for ident in sorted(GENERATED):
            entry = generated_by_id.get(ident, {})
            metadata_path = art / "audio" / f"{ident}.json"
            metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
            raw = art / "audio" / f"{ident}.wav"
            caf = runtime / f"{ident}.caf"
            detail = {"manifest_text": entry.get("text"), "returned_transcript": metadata.get("transcript"), "swift_text": lines.get(ident), "raw_sha256_expected": metadata.get("raw_sha256"), "raw_sha256_actual": sha256(raw) if raw.exists() else None, "runtime_sha256_expected": metadata.get("runtime_sha256"), "runtime_sha256_actual": sha256(caf) if caf.exists() else None}
            matches = all([metadata.get("id") == ident, entry.get("text") == lines.get(ident), metadata.get("transcript") == entry.get("text"), detail["raw_sha256_expected"] == detail["raw_sha256_actual"], detail["runtime_sha256_expected"] == detail["runtime_sha256_actual"]])
            generated_receipts[ident] = detail
            add(receipt, f"generated_{ident}", matches, detail)
        receipt["generated_transcripts"] = generated_receipts

        audio = {}
        for ident in IDS:
            detail = audio_signal(runtime / f"{ident}.caf")
            audio[ident] = detail
            add(receipt, f"audio_{ident}", detail["decodes"] and detail["sample_rate"] == 24000 and detail["channels"] == 1 and detail["no_long_silence"] and detail["not_clipped"], detail)
        receipt["audio"] = audio

        assets = root / "ios/Resources/Assets.xcassets"
        icon_catalog = json.loads((assets / "AppIcon.appiconset/Contents.json").read_text())
        icon = assets / "AppIcon.appiconset/AppIcon.png"
        icon_detail = image_properties(icon)
        icon_detail["catalog_filename"] = icon_catalog["images"][0].get("filename") if icon_catalog.get("images") else None
        add(receipt, "app_icon", icon_detail["width"] == icon_detail["height"] == 1024 and not icon_detail["has_alpha"] and icon_detail["catalog_filename"] == icon.name, icon_detail)
        cafe_catalog = json.loads((assets / "cafe-scene.imageset/Contents.json").read_text())
        cafe = assets / "cafe-scene.imageset/cafe-scene.png"
        cafe_detail = image_properties(cafe)
        cafe_detail["catalog_filename"] = cafe_catalog["images"][0].get("filename") if cafe_catalog.get("images") else None
        add(receipt, "cafe_scene_catalog", cafe.is_file() and cafe_detail["catalog_filename"] == cafe.name, cafe_detail)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as error:
        add(receipt, "validator_execution", False, str(error))

    serialized = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.write_receipt:
        (art / "validation.json").write_text(serialized, encoding="utf-8")
    sys.stdout.write(serialized)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
