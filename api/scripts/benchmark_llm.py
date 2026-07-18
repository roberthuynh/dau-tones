"""Ask the sibling Realtime model to name tones in its own validated speech."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly
from websockets.sync.client import connect

from dau.content import reference_corpus_is_complete, target_manifest
from dau.models import REFERENCE_MODEL
from dau.settings import DATA_ROOT, REPO_ROOT, openai_api_key
from dau.spend import approve, record
from dau.tones import canonical_tone, tone_family

OUTPUT_PATH = DATA_ROOT / "benchmark_llm.json"
REALTIME_URL = "wss://api.openai.com/v1/realtime"
TONE_NAMES = ("ngang", "huyen", "sac", "hoi", "nga", "nang")
ESTIMATED_REQUEST_USD = 0.012


def _audio_pcm24(path: Path) -> bytes:
    samples, rate = sf.read(path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)
    if rate != 24_000:
        divisor = np.gcd(rate, 24_000)
        samples = resample_poly(samples, 24_000 // divisor, rate // divisor)
    return (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()


def _ask(path: Path) -> tuple[str, dict[str, Any]]:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for an uncached benchmark")
    deltas: list[str] = []
    usage: dict[str, Any] = {}
    instructions = (
        "You are taking a closed-set Vietnamese phonetics test. Listen to one isolated "
        "Vietnamese word and identify its tone. Answer with exactly one ASCII label from: "
        "ngang, huyen, sac, hoi, nga, nang. Do not explain or infer from spelling because no "
        "spelling is provided."
    )
    with connect(
        f"{REALTIME_URL}?model={REFERENCE_MODEL}",
        additional_headers={"Authorization": f"Bearer {key}"},
        open_timeout=30,
        close_timeout=5,
    ) as websocket:
        websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": REFERENCE_MODEL,
                        "output_modalities": ["text"],
                        "reasoning": {"effort": "low"},
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": 24_000},
                                "turn_detection": None,
                            }
                        },
                        "instructions": instructions,
                    },
                }
            )
        )
        pcm = _audio_pcm24(path)
        for start in range(0, len(pcm), 24_000):
            websocket.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm[start : start + 24_000]).decode(),
                    }
                )
            )
        websocket.send(json.dumps({"type": "input_audio_buffer.commit"}))
        websocket.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {"output_modalities": ["text"], "max_output_tokens": 24},
                }
            )
        )
        while True:
            event = json.loads(websocket.recv(timeout=30))
            if event.get("type") == "response.output_text.delta":
                deltas.append(event.get("delta", ""))
            elif event.get("type") == "error":
                raise RuntimeError(event.get("error", {}).get("message", "Realtime error"))
            elif event.get("type") == "response.done":
                usage = event.get("response", {}).get("usage", {})
                if not deltas:
                    for output in event.get("response", {}).get("output", []):
                        for content in output.get("content", []):
                            if content.get("type") == "output_text":
                                deltas.append(content.get("text", ""))
                break
    return "".join(deltas).strip(), usage


def _normalize_answer(value: str) -> str | None:
    ascii_value = (
        value.casefold()
        .replace("huyền", "huyen")
        .replace("sắc", "sac")
        .replace("hỏi", "hoi")
        .replace("ngã", "nga")
        .replace("nặng", "nang")
    )
    matches = [name for name in TONE_NAMES if re.search(rf"\b{name}\b", ascii_value)]
    return matches[0] if len(matches) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if not reference_corpus_is_complete():
        raise RuntimeError(
            "The audio-model benchmark requires the complete validated target manifest."
        )
    manifest = target_manifest()
    targets = list(manifest.get("targets", []))
    if args.limit:
        targets = targets[: args.limit]
    cached = (
        json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        if OUTPUT_PATH.exists()
        else {"results": []}
    )
    cache_by_hash = {item["file_sha256"]: item for item in cached.get("results", [])}
    pending = [item for item in targets if item.get("sha256") not in cache_by_hash]
    approve(len(pending) * ESTIMATED_REQUEST_USD, f"audio-model benchmark ({len(pending)} files)")
    for target in pending:
        path = REPO_ROOT / target["path"]
        raw, usage = _ask(path)
        predicted = _normalize_answer(raw)
        actual = canonical_tone(target["tone"]).value
        accent = target["accent"]
        result = {
            "target_id": target["word_id"],
            "accent": accent,
            "model": REFERENCE_MODEL,
            "file_sha256": target["sha256"],
            "prompt_sha256": hashlib.sha256(b"closed-six-tone-label-benchmark-v1").hexdigest(),
            "actual_tone": actual,
            "raw_answer": raw,
            "predicted_tone": predicted,
            "exact_correct": predicted == actual,
            "family_correct": bool(
                predicted and tone_family(predicted, accent) == tone_family(actual, accent)
            ),
            "usage": usage,
        }
        cache_by_hash[target["sha256"]] = result
        record(
            f"benchmark:{accent}:{target['word_id']}",
            ESTIMATED_REQUEST_USD,
            usage,
        )
        print(
            f"{accent}/{target['word_id']}: {actual} -> {predicted or 'invalid'} "
            f"({'correct' if result['exact_correct'] else 'wrong'})"
        )
    results = [cache_by_hash[item["sha256"]] for item in targets]
    summary: dict[str, Any] = {}
    for accent in ("north", "south", "all"):
        rows = (
            results if accent == "all" else [item for item in results if item["accent"] == accent]
        )
        summary[accent] = {
            "samples": len(rows),
            "exact_accuracy": (
                sum(bool(item["exact_correct"]) for item in rows) / len(rows) if rows else 0.0
            ),
            "family_accuracy": (
                sum(bool(item["family_correct"]) for item in rows) / len(rows) if rows else 0.0
            ),
            "predictions": dict(Counter(item.get("predicted_tone") or "invalid" for item in rows)),
        }
    output = {
        "model": REFERENCE_MODEL,
        "method": "closed-set tone naming over DSP-validated sibling-model targets",
        "summary": summary,
        "results": results,
    }
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
