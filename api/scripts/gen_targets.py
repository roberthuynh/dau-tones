"""Generate Thầy Minh reference candidates and let DSP referee every target."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
from openai import OpenAI

from dau.content import inventory_document, word_surface
from dau.echo import normalize_text, tokens
from dau.models import REFERENCE_MODEL, TRANSCRIPTION_MODEL
from dau.realtime_audio import synthesize_utterance, voice_prompt
from dau.settings import TARGETS_ROOT, openai_api_key
from dau.spend import approve, record

TAKES_PER_WORD = 5
ESTIMATED_CANDIDATE_USD = 0.025
_SPEND_LOCK = threading.Lock()


def _validate(
    path: Path,
    word: dict[str, Any],
    accent: str,
    *,
    lexical_verified: bool,
) -> dict[str, Any]:
    from dau import tones

    if hasattr(tones, "validate_target_candidate"):
        result = tones.validate_target_candidate(
            path,
            expected_tone=word["tone"],
            accent=accent,
            lexical_verified=lexical_verified,
        )
        return result.as_dict() if hasattr(result, "as_dict") else result
    if hasattr(tones, "analyze_audio"):
        extracted = tones.analyze_audio(path)
        return {
            "passed": True,
            "contour": extracted.as_dict()["contour"],
            "features": extracted.as_dict()["features"],
            "score": 0.0,
            "reason_codes": [],
        }
    raise RuntimeError("DSP target validation entry point is unavailable")


def _trim_carrier(source: Path, destination: Path) -> None:
    samples, sample_rate = sf.read(source, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)
    intervals = librosa.effects.split(samples, top_db=30, frame_length=1024, hop_length=256)
    if not len(intervals):
        destination.write_bytes(source.read_bytes())
        return
    midpoint = samples.size / 2
    start, end = min(
        intervals, key=lambda interval: abs(((interval[0] + interval[1]) / 2) - midpoint)
    )
    pad = round(0.08 * sample_rate)
    start = max(0, int(start) - pad)
    end = min(samples.size, int(end) + pad)
    sf.write(destination, samples[start:end], sample_rate, subtype="PCM_16")


def _lexical_identity(path: Path, word: dict[str, Any]) -> tuple[bool, str]:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for lexical validation")
    client = OpenAI(api_key=key, timeout=30, max_retries=1)
    with path.open("rb") as audio:
        result = client.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=audio,
            language="vi",
            prompt=(
                "Transcribe this isolated Vietnamese word exactly in Unicode NFC. Do not add "
                "punctuation or silently correct its tone mark."
            ),
            response_format="text",
        )
    transcript = result if isinstance(result, str) else result.text
    heard = tokens(transcript)
    expected = normalize_text(word_surface(word))
    matched = len(heard) == 1 and unicodedata.normalize("NFC", heard[0]) == expected
    return matched, unicodedata.normalize("NFC", transcript).strip()


def _candidate_text(word: dict[str, Any], source_mode: str) -> str:
    if source_mode == "isolated":
        return word_surface(word)
    return f"Từ ... {word_surface(word)} ... nhé."


def _generate_candidate(
    word: dict[str, Any], accent: str, source_mode: str, take: int
) -> dict[str, Any]:
    candidate_dir = TARGETS_ROOT / "candidates" / accent / word["id"] / source_mode
    candidate_dir.mkdir(parents=True, exist_ok=True)
    path = candidate_dir / f"take-{take}.wav"
    if not path.exists():
        instructions = voice_prompt(accent) + " Preserve the exact lexical identity and tone. "
        instructions += (
            "Speak the short carrier exactly once. Leave about 400 milliseconds of silence "
            "before and after its middle requested word."
            if source_mode == "carrier"
            else "Speak the requested word in isolation. Do not add any other words."
        )
        try:
            wav = synthesize_utterance(
                _candidate_text(word, source_mode),
                accent=accent,
                model=REFERENCE_MODEL,
                instructions=instructions,
                max_output_tokens=192,
                allow_incomplete_audio=source_mode == "carrier",
            )
        except Exception as error:
            with _SPEND_LOCK:
                record(
                    f"target:{accent}:{word['id']}:{source_mode}:{take}",
                    ESTIMATED_CANDIDATE_USD,
                    {"status": "failed", "error_type": type(error).__name__},
                )
            validation = {
                "passed": False,
                "reason_codes": ["generation_error"],
                "error": str(error),
            }
            print(
                f"{accent}/{word_surface(word)} {source_mode} take {take}: reject generation_error"
            )
            return {
                "take": take,
                "path": str(path.relative_to(TARGETS_ROOT.parent)),
                "source_mode": source_mode,
                "sha256": None,
                "validation": validation,
            }
        if source_mode == "carrier":
            raw_path = candidate_dir / f"take-{take}.raw.wav"
            raw_path.write_bytes(wav)
            _trim_carrier(raw_path, path)
        else:
            path.write_bytes(wav)
        with _SPEND_LOCK:
            record(
                f"target:{accent}:{word['id']}:{source_mode}:{take}",
                ESTIMATED_CANDIDATE_USD,
                {"status": "completed"},
            )
    try:
        lexical_verified, transcript = _lexical_identity(path, word)
        validation = _validate(
            path,
            word,
            accent,
            lexical_verified=lexical_verified,
        )
        validation["transcript"] = transcript
        validation["lexical_verified"] = lexical_verified
    except Exception as error:
        validation = {
            "passed": False,
            "reason_codes": ["validation_error"],
            "error": str(error),
        }
    candidate = {
        "take": take,
        "path": str(path.relative_to(TARGETS_ROOT.parent)),
        "source_mode": source_mode,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "validation": validation,
    }
    print(
        f"{accent}/{word_surface(word)} {source_mode} take {take}: "
        f"{'PASS' if validation.get('passed') else 'reject'} "
        f"{','.join(validation.get('reason_codes', []))}"
    )
    return candidate


def _generate_candidates(
    word: dict[str, Any], accent: str, source_mode: str, *, workers: int
) -> list[dict[str, Any]]:
    with ThreadPoolExecutor(max_workers=min(workers, TAKES_PER_WORD)) as executor:
        candidates = list(
            executor.map(
                lambda take: _generate_candidate(word, accent, source_mode, take),
                range(1, TAKES_PER_WORD + 1),
            )
        )
    return sorted(candidates, key=lambda candidate: int(candidate["take"]))


def _choose(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    passing = [candidate for candidate in candidates if candidate["validation"].get("passed")]
    if not passing:
        return None
    return max(
        passing,
        key=lambda item: (
            float(
                item["validation"].get("separation_margin", item["validation"].get("score", 0.0))
            ),
            float(item["validation"].get("voicing_probability", 0.0)),
            -int(item["take"]),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accent", choices=["north", "south", "both"], default="both")
    parser.add_argument("--word", action="append", default=[])
    parser.add_argument(
        "--known-failed-pair",
        action="append",
        default=[],
        metavar="ACCENT/WORD_ID",
        help="Skip an already exhausted pair while retaining it as a manifest-blocking failure.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workers", type=int, choices=range(1, 6), default=5)
    args = parser.parse_args()
    accents = ["north", "south"] if args.accent == "both" else [args.accent]
    words = [
        word
        for word in inventory_document().get("words", [])
        if not args.word or word["id"] in args.word or word_surface(word) in args.word
    ]
    words_by_id = {word["id"]: word for word in words}
    known_failed_pairs = set(args.known_failed_pair)
    valid_pair_ids = {f"{accent}/{word['id']}" for accent in accents for word in words}
    invalid_pair_ids = sorted(known_failed_pairs - valid_pair_ids)
    if invalid_pair_ids:
        parser.error(f"unknown --known-failed-pair values: {', '.join(invalid_pair_ids)}")
    jobs = [
        (accent, word)
        for accent in accents
        for word in words
        if f"{accent}/{word['id']}" not in known_failed_pairs
    ]
    maximum_calls = len(jobs) * TAKES_PER_WORD * 2
    approve(
        maximum_calls * ESTIMATED_CANDIDATE_USD,
        f"reference candidates (worst case {maximum_calls})",
    )
    if args.dry_run:
        for accent, word in jobs:
            print(accent, voice_prompt(accent))
            print(f"  {word['id']}: {_candidate_text(word, 'isolated')}")
        for pair_id in sorted(known_failed_pairs):
            print(f"  known failure, skipped: {pair_id}")
        return

    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for pair_id in sorted(known_failed_pairs):
        accent, word_id = pair_id.split("/", 1)
        word = words_by_id[word_id]
        failures.append(
            {
                "pair_id": pair_id,
                "accent": accent,
                "word_id": word_id,
                "surface": word_surface(word),
                "tone": word["tone"],
                "reason": "known_exhausted_pair",
            }
        )
    for accent, word in jobs:
        candidates = _generate_candidates(word, accent, "isolated", workers=args.workers)
        choice = _choose(candidates)
        if choice is None:
            carrier = _generate_candidates(word, accent, "carrier", workers=args.workers)
            candidates.extend(carrier)
            choice = _choose(carrier)
        rejected.extend(
            {
                "word_id": word["id"],
                "surface": word_surface(word),
                "tone": word["tone"],
                "accent": accent,
                **candidate,
            }
            for candidate in candidates
            if choice is None or candidate["path"] != choice["path"]
        )
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
            continue
        source = TARGETS_ROOT.parent / choice["path"]
        destination = TARGETS_ROOT / accent / f"{word['id']}.wav"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
        selected.append(
            {
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
        )
    report = {
        "schema_version": 1,
        "status": "blocked" if failures else "validated",
        "model": REFERENCE_MODEL,
        "voice": "cedar",
        "candidate_takes_per_word_accent": TAKES_PER_WORD,
        "known_failed_pairs_skipped": sorted(known_failed_pairs),
        "targets": selected,
        "rejected": rejected,
        "failures": failures,
    }
    report_path = TARGETS_ROOT / "generation-report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if failures:
        print("No DSP-validated target for:", file=sys.stderr)
        print(
            "\n".join(
                f"  {failure['accent']}/{failure['surface']} ({failure['word_id']})"
                for failure in failures
            ),
            file=sys.stderr,
        )
        print(f"Detailed audit written to {report_path}", file=sys.stderr)
        print("Stop gate reached. Record these items on a phone before shipping.", file=sys.stderr)
        raise SystemExit(2)
    manifest = {
        "schema_version": 1,
        "model": REFERENCE_MODEL,
        "voice": "cedar",
        "candidate_takes_per_word_accent": TAKES_PER_WORD,
        "targets": selected,
        "rejected": rejected,
    }
    (TARGETS_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"validated {len(selected)} targets; manifest written to {TARGETS_ROOT / 'manifest.json'}"
    )


if __name__ == "__main__":
    main()
