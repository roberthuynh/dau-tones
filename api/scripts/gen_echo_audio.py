"""Generate and validate all 52 dual-accent dialogue utterances."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from dau.content import echo_document
from dau.echo import tokens
from dau.models import REFERENCE_MODEL, SPEECH_MODEL, TRANSCRIPTION_MODEL
from dau.settings import TARGETS_ROOT, openai_api_key
from dau.spend import approve, load_ledger, record

ESTIMATED_UTTERANCE_USD = 0.035


def synthesize_utterance(text: str, *, accent: str, model: str) -> bytes:
    """Keep Realtime networking imports out of validation-only script paths."""

    from dau.realtime_audio import synthesize_utterance as synthesize
    from dau.realtime_audio import voice_prompt

    output_cap = min(1_024, max(512, len(tokens(text)) * 64))
    instructions = (
        voice_prompt(accent)
        + " Exact-copy rule: speak every Vietnamese word exactly as written in the user's "
        "sentence. Never paraphrase, shorten, omit, or substitute a synonym or pronoun. "
        "Preserve every name and tone carefully."
    )
    if text.startswith("Tuyệt quá"):
        instructions += (
            " For this sentence, begin cleanly with the full word ‘Tuyệt’, including its "
            "initial T and final T, pause briefly after ‘quá’, then say ‘Má bạn’ exactly."
        )
    if "mạ cửa" in text or "Mạ." in text:
        instructions += (
            " This sentence is intentionally absurd for a tone lesson. Pronounce ‘mạ cửa’ "
            "exactly as written: mạ means rice seedling and uses dấu nặng, with a short, low, "
            "stopped vowel. Do not correct it to mã cửa."
        )
    if text.strip(" .,!?").casefold() == "phờ":
        instructions += (
            " Say the syllable phờ in isolation with the same ơ vowel as phở, but with a clear "
            "falling dấu huyền. Do not say phở."
        )
    return synthesize(
        text,
        accent=accent,
        model=model,
        instructions=instructions,
        max_output_tokens=output_cap,
    )


def _transcribe(path: Path) -> str:
    from openai import OpenAI

    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required to validate Echo speech")
    client = OpenAI(api_key=key, timeout=30, max_retries=1)
    with path.open("rb") as audio:
        result = client.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=audio,
            language="vi",
            prompt=(
                "Transcribe this Vietnamese sentence exactly in Unicode NFC. Preserve every "
                "tone mark and do not add commentary."
            ),
            response_format="text",
        )
    return (result if isinstance(result, str) else result.text).strip()


def _contour_quality(path: Path) -> dict[str, Any]:
    import librosa
    import numpy as np
    import soundfile as sf  # type: ignore[import-untyped]

    samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)
    duration = samples.size / sample_rate
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    clipping = float(np.mean(np.abs(samples) >= 0.995)) if samples.size else 0.0
    f0, voiced, _ = librosa.pyin(
        samples,
        fmin=65,
        fmax=650,
        sr=sample_rate,
        frame_length=1024,
        hop_length=256,
    )
    voiced_fraction = float(np.mean(voiced)) if voiced.size else 0.0
    passed = (
        0.5 <= duration <= 12.0
        and 0.02 <= peak < 0.995
        and rms >= 0.005
        and clipping <= 0.001
        and voiced_fraction >= 0.15
        and bool(np.any(np.isfinite(f0)))
    )
    return {
        "passed": passed,
        "duration_s": round(duration, 4),
        "peak": round(peak, 6),
        "rms": round(rms, 6),
        "clipping_fraction": round(clipping, 6),
        "voiced_fraction": round(voiced_fraction, 6),
    }


NUMBER_WORDS = {
    "0": "không",
    "1": "một",
    "2": "hai",
    "3": "ba",
    "4": "bốn",
    "5": "năm",
    "6": "sáu",
    "7": "bảy",
    "8": "tám",
    "9": "chín",
}


def _lexical_tokens(value: str) -> list[str]:
    expanded = re.sub(
        r"\d+",
        lambda match: " ".join(NUMBER_WORDS[digit] for digit in match.group()),
        value,
    )
    return tokens(expanded)


def _validate(path: Path, expected: str) -> dict[str, Any]:
    transcript = _transcribe(path)
    lexical_verified = _lexical_tokens(transcript) == _lexical_tokens(expected)
    contour_quality = _contour_quality(path)
    return {
        "passed": lexical_verified and contour_quality["passed"],
        "transcript": transcript,
        "lexical_verified": lexical_verified,
        "contour_quality": contour_quality,
    }


def _generate_validated(
    text: str,
    accent: str,
    destination: Path,
    *,
    expected_text: str | None = None,
) -> tuple[str, dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for model in (SPEECH_MODEL, REFERENCE_MODEL):
        candidate = destination.with_name(f".{destination.stem}.{model}.candidate.wav")
        try:
            candidate.write_bytes(synthesize_utterance(text, accent=accent, model=model))
            validation = _validate(candidate, expected_text or text)
        except Exception as error:
            validation = {
                "passed": False,
                "error_type": type(error).__name__,
                "error": str(error),
            }
        record(
            f"echo:{accent}:{destination.stem}:{model}",
            ESTIMATED_UTTERANCE_USD,
            {"validation": validation},
        )
        attempts.append({"model": model, "validation": validation})
        if validation.get("passed"):
            candidate.replace(destination)
            return model, {"selected": validation, "attempts": attempts}
        candidate.unlink(missing_ok=True)
    raise RuntimeError(
        f"Echo speech failed ASR/contour validation for {accent}/{destination.stem}: {attempts}"
    )


def _receipt_entry(
    *,
    turn_id: str,
    scene_id: str,
    speaker: str,
    accent: str,
    path: Path,
    model: str,
    validation: dict[str, Any],
) -> dict[str, Any]:
    wav = path.read_bytes()
    return {
        "turn_id": turn_id,
        "sentence_id": turn_id,
        "scene_id": scene_id,
        "speaker": speaker,
        "accent": accent,
        "model": model,
        "provider_voice": "cedar",
        "display_voice": "Thầy Minh",
        "path": str(path.relative_to(TARGETS_ROOT.parent)),
        "sha256": hashlib.sha256(wav).hexdigest(),
        "validation": validation,
        "quality_note": "Realtime mini passed ASR and contour-presence checks"
        if model == SPEECH_MODEL
        else "Realtime full model passed after mini failed ASR or contour-presence checks",
    }


def _entry_is_current(entry: dict[str, Any] | None, path: Path) -> bool:
    if not entry or not path.is_file():
        return False
    validation = entry.get("validation", {}).get("selected", {})
    return bool(
        validation.get("passed")
        and entry.get("sha256") == hashlib.sha256(path.read_bytes()).hexdigest()
        and entry.get("model") in {SPEECH_MODEL, REFERENCE_MODEL}
    )


def _recover_cached_receipt(
    *, turn_id: str, accent: str, path: Path
) -> tuple[str, dict[str, Any]] | None:
    """Recover an interrupted run without paying to regenerate already validated audio."""

    if not path.is_file():
        return None
    current_quality = _contour_quality(path)
    if not current_quality["passed"]:
        return None
    prefix = f"echo:{accent}:{turn_id}:"
    for event in reversed(load_ledger().get("events", [])):
        label = str(event.get("label", ""))
        if not label.startswith(prefix):
            continue
        model = label.removeprefix(prefix)
        validation = event.get("usage", {}).get("validation", {})
        if model not in {SPEECH_MODEL, REFERENCE_MODEL} or not validation.get("passed"):
            continue
        selected = dict(validation)
        selected["contour_quality"] = current_quality
        return model, {"selected": selected, "attempts": [{"model": model, "validation": selected}]}
    return None


def _write_manifest(path: Path, entries: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "provider_voice": "cedar",
                "display_voice": "Thầy Minh",
                "primary_model": SPEECH_MODEL,
                "fallback_model": REFERENCE_MODEL,
                "validation": [
                    f"exact Vietnamese token match from {TRANSCRIPTION_MODEL}",
                    "signal quality and pYIN contour presence",
                ],
                "expected_utterance_count": 52,
                "utterances": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--concurrency", type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    output_dir = TARGETS_ROOT / "echo"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.exists()
        else {"utterances": []}
    )
    existing_by_key = {
        (item.get("turn_id") or item["sentence_id"], item["accent"]): item
        for item in manifest.get("utterances", [])
    }
    turns = echo_document().get("turns", [])
    ordered_keys = [(turn["id"], accent) for turn in turns for accent in ("north", "south")]
    expected_keys = set(ordered_keys)
    by_key = {key: value for key, value in existing_by_key.items() if key in expected_keys}
    work = []
    for turn in turns:
        for accent in ("north", "south"):
            path = TARGETS_ROOT.parent / turn["shadow_audio"][accent]
            key = (turn["id"], accent)
            if _entry_is_current(by_key.get(key), path):
                continue
            recovered = _recover_cached_receipt(turn_id=turn["id"], accent=accent, path=path)
            if recovered:
                model, validation = recovered
                by_key[key] = _receipt_entry(
                    turn_id=turn["id"],
                    scene_id=turn["scene_id"],
                    speaker=turn["speaker"],
                    accent=accent,
                    path=path,
                    model=model,
                    validation=validation,
                )
                continue
            work.append((turn, accent, path))
    if by_key and not args.dry_run:
        _write_manifest(manifest_path, [by_key[key] for key in ordered_keys if key in by_key])
    approve(
        len(work) * ESTIMATED_UTTERANCE_USD * 2,
        f"Echo speech ({len(work)} utterances, including full-model fallback allowance)",
    )
    if args.dry_run:
        for turn, accent, path in work:
            print(accent, turn["id"], turn["text"], path)
        return
    if work:
        # Warm pYIN once before worker threads touch its JIT cache.
        _contour_quality(TARGETS_ROOT / "north" / "ma-ghost.wav")

    def generate_job(
        item: tuple[dict[str, Any], str, Path],
    ) -> tuple[tuple[str, str], dict[str, Any]]:
        turn, accent, path = item
        path.parent.mkdir(parents=True, exist_ok=True)
        selected_model, validation = _generate_validated(turn["text"], accent, path)
        return (
            (turn["id"], accent),
            _receipt_entry(
                turn_id=turn["id"],
                scene_id=turn["scene_id"],
                speaker=turn["speaker"],
                accent=accent,
                path=path,
                model=selected_model,
                validation=validation,
            ),
        )

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = {executor.submit(generate_job, item): item for item in work}
        for future in as_completed(futures):
            turn, accent, path = futures[future]
            try:
                key, entry = future.result()
            except Exception as error:
                failures.append(f"{accent}/{turn['id']}: {error}")
                print(f"failed {accent}/{turn['id']}: {error}")
                continue
            by_key[key] = entry
            _write_manifest(manifest_path, [by_key[key] for key in ordered_keys if key in by_key])
            print(f"generated {path} with {entry['model']}")
    if failures:
        raise RuntimeError("Echo generation failures:\n" + "\n".join(failures))
    missing = [key for key in ordered_keys if key not in by_key]
    if missing:
        raise RuntimeError(f"Echo manifest is incomplete: {missing}")


if __name__ == "__main__":
    main()
