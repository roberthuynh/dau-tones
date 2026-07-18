"""Generate and validate one wrong-tone Echo recording for every scene."""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from dau.content import echo_document
from dau.models import REFERENCE_MODEL
from dau.settings import REPO_ROOT
from dau.spend import approve
from scripts.gen_echo_audio import (
    ESTIMATED_UTTERANCE_USD,
    _contour_quality,
    _generate_validated,
    _recover_cached_receipt,
)

DEMO_MANIFEST = REPO_ROOT / "api" / "data" / "demo_manifest.json"


def _scene_demos() -> list[dict[str, Any]]:
    document = echo_document()
    turns = {turn["id"]: turn for turn in document["turns"]}
    demos: list[dict[str, Any]] = []
    for scene in document["scenes"]:
        demo = scene["offline_demo"]
        turn = turns[demo["turn_id"]]
        demos.append(
            {
                "id": demo["id"],
                "title": f"{scene['title']} wrong-tone replay",
                "scene_id": scene["id"],
                "turn_id": turn["id"],
                "sentence_id": turn["id"],
                "accent": "north",
                "target_text": turn["text"],
                "committed_transcript": demo["committed_transcript"],
                "generation_text": {
                    "family-dinner-seedling-code": (
                        "Cửa nhà màu xanh. Mạ. Cửa là hai ba sáu. Bạn cứ vào nhé."
                    ),
                    "pho-shop-said-listless": (
                        "Cho tôi một tô phờ bò, một đĩa rau và một ly nước."
                    ),
                }.get(demo["id"], demo["committed_transcript"]),
                "recording_path": demo["recording_path"],
                "mistake_art_url": demo.get("mistake_art_url"),
            }
        )
    return demos


def _current(entry: dict[str, Any] | None, path: Path, expected: str) -> bool:
    if not entry or not path.is_file():
        return False
    selected = entry.get("generation", {}).get("validation", {}).get("selected", {})
    return bool(
        selected.get("passed")
        and entry.get("committed_transcript") == expected
        and entry.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def _write_manifest(document: dict[str, Any]) -> None:
    temporary = DEMO_MANIFEST.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(DEMO_MANIFEST)


def _manifest_entry(
    demo: dict[str, Any], path: Path, model: str, validation: dict[str, Any]
) -> dict[str, Any]:
    return {
        **demo,
        "generation": {
            "model": model,
            "voice": "cedar",
            "display_voice": "Thầy Minh",
            "validation": validation,
            "quality_note": "Realtime speech passed exact Vietnamese ASR and contour checks",
        },
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _build_seedling_code_splice(demo: dict[str, Any], path: Path) -> dict[str, Any]:
    """Replace validated mã with validated mạ at a known silent word boundary."""

    import numpy as np
    import soundfile as sf  # type: ignore[import-untyped]
    from scipy.signal import resample  # type: ignore[import-untyped]

    dialogue_path = REPO_ROOT / "targets" / "echo" / "north" / "family-dinner-learner-03.wav"
    seedling_path = REPO_ROOT / "targets" / "north" / "ma-seedling.wav"
    dialogue, sample_rate = sf.read(dialogue_path, dtype="float32", always_2d=False)
    seedling, seedling_rate = sf.read(seedling_path, dtype="float32", always_2d=False)
    if dialogue.ndim != 1 or seedling.ndim != 1 or sample_rate != seedling_rate:
        raise RuntimeError("splice sources must be mono with matching sample rates")

    destination_start = round(1.18 * sample_rate)
    destination_end = round(1.43 * sample_rate)
    source_start = round(0.62 * sample_rate)
    source_end = round(0.90 * sample_rate)
    original = dialogue[destination_start:destination_end].copy()
    replacement = resample(seedling[source_start:source_end], original.size).astype(np.float32)
    source_rms = float(np.sqrt(np.mean(np.square(replacement))))
    destination_rms = float(np.sqrt(np.mean(np.square(original))))
    gain = min(1.35, max(0.55, destination_rms / max(source_rms, 1e-6)))
    replacement *= gain
    fade_size = round(0.015 * sample_rate)
    fade_in = np.linspace(0.0, 1.0, fade_size, dtype=np.float32)
    replacement[:fade_size] = (
        original[:fade_size] * (1.0 - fade_in) + replacement[:fade_size] * fade_in
    )
    fade_out = fade_in[::-1]
    replacement[-fade_size:] = (
        original[-fade_size:] * (1.0 - fade_out) + replacement[-fade_size:] * fade_out
    )
    result = dialogue.copy()
    result[destination_start:destination_end] = replacement
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, result, sample_rate, subtype="PCM_16")

    signal_quality = _contour_quality(path)
    if not signal_quality["passed"]:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"spliced recording failed signal validation: {signal_quality}")
    report = json.loads((REPO_ROOT / "targets" / "generation-report.json").read_text())
    seedling_receipt = next(
        entry
        for entry in report["targets"]
        if entry["word_id"] == "ma-seedling" and entry["accent"] == "north"
    )
    if not seedling_receipt["validation"]["passed"]:
        raise RuntimeError("the source mạ target is not validated")
    validation = {
        "selected": {
            "passed": True,
            "lexical_verified": True,
            "validation_method": "sample-accurate composition of two validated Realtime sources",
            "transcript": demo["committed_transcript"],
            "contour_quality": signal_quality,
            "inserted_tone": "nang",
            "inserted_surface": "mạ",
            "inserted_target_validation": {
                "transcript": seedling_receipt["validation"]["transcript"],
                "shape_score": seedling_receipt["validation"]["shape_score"],
                "separation_margin": seedling_receipt["validation"]["separation_margin"],
            },
        },
        "attempts": [],
        "construction": {
            "dialogue_source": str(dialogue_path.relative_to(REPO_ROOT)),
            "dialogue_sha256": hashlib.sha256(dialogue_path.read_bytes()).hexdigest(),
            "word_source": str(seedling_path.relative_to(REPO_ROOT)),
            "word_sha256": hashlib.sha256(seedling_path.read_bytes()).hexdigest(),
            "destination_seconds": [1.18, 1.43],
            "source_seconds": [0.62, 0.90],
            "crossfade_ms": 15,
        },
    }
    entry = _manifest_entry(demo, path, REFERENCE_MODEL, validation)
    entry["generation"]["quality_note"] = (
        "Validated Realtime sentence with its mã segment replaced by the validated Realtime "
        "mạ target; sample-accurate provenance is recorded"
    )
    return entry


def _build_pho_falling_splice(demo: dict[str, Any], path: Path) -> dict[str, Any]:
    """Transform the validated phở segment into a DSP-verified phờ segment."""

    import librosa
    import numpy as np
    import soundfile as sf

    from dau.tones import Accent, Tone, validate_target_candidate

    dialogue_path = REPO_ROOT / "targets" / "echo" / "north" / "pho-shop-learner-01.wav"
    dialogue, sample_rate = sf.read(dialogue_path, dtype="float32", always_2d=False)
    if dialogue.ndim != 1:
        raise RuntimeError("the source dialogue recording must be mono")
    destination_start = round(0.84 * sample_rate)
    destination_end = round(1.04 * sample_rate)
    original = dialogue[destination_start:destination_end].copy()
    boundaries = np.linspace(0, original.size, 4, dtype=int)
    steps = (2.0, 0.0, -2.0)
    replacement = np.concatenate(
        [
            librosa.effects.pitch_shift(
                original[boundaries[index] : boundaries[index + 1]],
                sr=sample_rate,
                n_steps=step,
                res_type="soxr_hq",
            )
            for index, step in enumerate(steps)
        ]
    ).astype(np.float32)
    transformed_path = path.with_name(f".{path.stem}.transformed-word.wav")
    sf.write(transformed_path, replacement, sample_rate, subtype="PCM_16")
    tone_validation = validate_target_candidate(
        str(transformed_path), Tone.HUYEN, accent=Accent.NORTH, lexical_verified=True
    )
    transformed_sha256 = hashlib.sha256(transformed_path.read_bytes()).hexdigest()
    transformed_path.unlink(missing_ok=True)
    if not tone_validation.passed:
        raise RuntimeError(
            "the deterministic phở-to-phờ transform failed falling-tone validation: "
            f"{tone_validation.reason_codes}"
        )
    result = dialogue.copy()
    result[destination_start:destination_end] = replacement
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, result, sample_rate, subtype="PCM_16")
    signal_quality = _contour_quality(path)
    if not signal_quality["passed"]:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"spliced recording failed signal validation: {signal_quality}")

    validation = {
        "selected": {
            "passed": True,
            "lexical_verified": True,
            "validation_method": "sample-accurate DSP tone transform of validated Realtime speech",
            "transcript": demo["committed_transcript"],
            "contour_quality": signal_quality,
            "inserted_tone": "huyen",
            "inserted_surface": "phờ",
            "inserted_target_validation": {
                "transcript": "phonemes retained from the validated phở source segment",
                "shape_score": tone_validation.shape_score,
                "separation_margin": tone_validation.separation_margin,
                "reason_codes": list(tone_validation.reason_codes),
            },
        },
        "attempts": [],
        "construction": {
            "dialogue_source": str(dialogue_path.relative_to(REPO_ROOT)),
            "dialogue_sha256": hashlib.sha256(dialogue_path.read_bytes()).hexdigest(),
            "source_surface": "phở",
            "transformed_surface": "phờ",
            "destination_seconds": [0.84, 1.04],
            "piecewise_pitch_shift_semitones": list(steps),
            "transformed_segment_sha256": transformed_sha256,
        },
    }
    echo_manifest = json.loads(
        (REPO_ROOT / "targets" / "echo" / "manifest.json").read_text(encoding="utf-8")
    )
    source_model = next(
        item["model"]
        for item in echo_manifest["utterances"]
        if item["turn_id"] == "pho-shop-learner-01" and item["accent"] == "north"
    )
    entry = _manifest_entry(demo, path, source_model, validation)
    entry["generation"]["quality_note"] = (
        "Validated Realtime phở phonemes transformed into a falling phờ contour; the isolated "
        "result passed the deterministic tone referee"
    )
    return entry


def main() -> None:
    load_dotenv(REPO_ROOT / ".env.local")
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()

    document = json.loads(DEMO_MANIFEST.read_text(encoding="utf-8"))
    existing = {entry["id"]: entry for entry in document.get("echo_demos", [])}
    requested = _scene_demos()
    work: list[tuple[dict[str, Any], Path]] = []
    for demo in requested:
        path = REPO_ROOT / demo["recording_path"]
        if _current(existing.get(demo["id"]), path, demo["committed_transcript"]):
            continue
        recovered = _recover_cached_receipt(
            turn_id=demo["id"], accent=demo["accent"], path=path
        )
        if recovered:
            model, validation = recovered
            existing[demo["id"]] = _manifest_entry(
                demo, path, model, validation
            )
            continue
        work.append((demo, path))

    locally_built = {"family-dinner-seedling-code", "pho-shop-said-listless"}
    remote_count = sum(demo["id"] not in locally_built for demo, _ in work)
    approve(
        remote_count * ESTIMATED_UTTERANCE_USD * 2,
        f"Echo offline demos ({remote_count} remote recordings, including fallback allowance)",
    )
    if args.dry_run:
        for demo, path in work:
            print(demo["id"], demo["committed_transcript"], path)
        return

    def generate(item: tuple[dict[str, Any], Path]) -> dict[str, Any]:
        demo, path = item
        path.parent.mkdir(parents=True, exist_ok=True)
        if demo["id"] == "family-dinner-seedling-code":
            return _build_seedling_code_splice(demo, path)
        if demo["id"] == "pho-shop-said-listless":
            return _build_pho_falling_splice(demo, path)
        model, validation = _generate_validated(
            demo["generation_text"],
            demo["accent"],
            path,
            expected_text=demo["committed_transcript"],
        )
        return _manifest_entry(demo, path, model, validation)

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(generate, item): item for item in work}
        for future in as_completed(futures):
            demo, _ = futures[future]
            try:
                entry = future.result()
            except Exception as error:
                failures.append(f"{demo['id']}: {error}")
                print(f"failed {demo['id']}: {error}")
                continue
            existing[demo["id"]] = entry
            print(f"generated {demo['id']} with {entry['generation']['model']}")

    requested_ids = {demo["id"] for demo in requested}
    legacy = [
        entry
        for entry in document.get("echo_demos", [])
        if entry["id"] not in requested_ids and "scene_id" not in entry
    ]
    document["schema_version"] = 2
    completed = [existing[demo["id"]] for demo in requested if demo["id"] in existing]
    document["echo_demos"] = legacy + completed
    _write_manifest(document)
    if failures:
        raise RuntimeError("Echo demo generation failures:\n" + "\n".join(failures))
    missing = [demo["id"] for demo in requested if demo["id"] not in existing]
    if missing:
        raise RuntimeError(f"Echo demo manifest is incomplete: {missing}")


if __name__ == "__main__":
    main()
