"""Ask the sibling Realtime model to name tones in its own validated speech."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import numpy as np
import soundfile as sf  # type: ignore[import-untyped]
from scipy.signal import resample_poly  # type: ignore[import-untyped]
from websockets.sync.client import connect

from dau.content import reference_corpus_is_complete, target_manifest
from dau.models import REFERENCE_MODEL
from dau.settings import DATA_ROOT, REPO_ROOT, TARGETS_ROOT, openai_api_key
from dau.spend import approve, record
from dau.tones import canonical_accent, canonical_tone, tone_family

OUTPUT_PATH = DATA_ROOT / "benchmark_llm.json"
EVALUATION_PATH = DATA_ROOT / "evaluation.json"
MANIFEST_PATH = TARGETS_ROOT / "manifest.json"
REALTIME_URL = "wss://api.openai.com/v1/realtime"
TONE_NAMES = ("ngang", "huyen", "sac", "hoi", "nga", "nang")
ESTIMATED_REQUEST_USD = 0.012
SCHEMA_VERSION = 2
BENCHMARK_PROMPT = (
    "You are taking a closed-set Vietnamese phonetics test. Listen to one isolated "
    "Vietnamese word and identify its tone. Answer with exactly one ASCII label from: "
    "ngang, huyen, sac, hoi, nga, nang. Do not explain or infer from spelling because no "
    "spelling is provided."
)
PROMPT_SHA256 = hashlib.sha256(BENCHMARK_PROMPT.encode()).hexdigest()


@dataclass(frozen=True)
class BenchmarkCase:
    target_id: str
    accent: str
    actual_tone: str
    path: Path
    file_sha256: str
    model: str
    prompt_sha256: str
    case_sha256: str


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _case_sha256(
    *,
    target_id: str,
    accent: str,
    actual_tone: str,
    file_sha256: str,
    model: str = REFERENCE_MODEL,
    prompt_sha256: str = PROMPT_SHA256,
) -> str:
    return _canonical_json_sha256(
        {
            "target_id": target_id,
            "accent": accent,
            "actual_tone": actual_tone,
            "file_sha256": file_sha256,
            "model": model,
            "prompt_sha256": prompt_sha256,
        }
    )


def _benchmark_cases(
    manifest: Mapping[str, Any],
    *,
    repo_root: Path = REPO_ROOT,
) -> list[BenchmarkCase]:
    """Resolve and hash-check every benchmark case before using cache or API."""

    root = repo_root.resolve()
    raw_targets = manifest.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("The target manifest does not contain benchmark targets")
    cases: list[BenchmarkCase] = []
    identities: set[tuple[str, str]] = set()
    for target in raw_targets:
        if not isinstance(target, Mapping):
            raise ValueError("Every benchmark target must be an object")
        target_id = str(target.get("word_id", "")).strip()
        accent = canonical_accent(str(target.get("accent", ""))).value
        actual_tone = canonical_tone(str(target.get("tone", ""))).value
        if not target_id:
            raise ValueError("Every benchmark target needs a word_id")
        identity = (target_id, accent)
        if identity in identities:
            raise ValueError(f"Duplicate benchmark target: {accent}/{target_id}")
        identities.add(identity)
        validation = target.get("validation")
        if not isinstance(validation, Mapping) or validation.get("passed") is not True:
            raise ValueError(f"Benchmark target {accent}/{target_id} is not DSP-validated")
        relative_path = target.get("path")
        if not isinstance(relative_path, str) or not relative_path:
            raise ValueError(f"Benchmark target {accent}/{target_id} has no path")
        unresolved_path = Path(relative_path)
        if unresolved_path.is_absolute():
            raise ValueError(f"Benchmark target {accent}/{target_id} uses an absolute path")
        path = (root / unresolved_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Benchmark target {accent}/{target_id} escapes the repository")
        if not path.is_file():
            raise ValueError(f"Benchmark target {accent}/{target_id} is missing: {path}")
        expected_hash = target.get("sha256")
        actual_hash = _sha256_file(path)
        if not isinstance(expected_hash, str) or expected_hash.casefold() != actual_hash:
            raise ValueError(
                f"Benchmark target {accent}/{target_id} SHA-256 mismatch: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        case_hash = _case_sha256(
            target_id=target_id,
            accent=accent,
            actual_tone=actual_tone,
            file_sha256=actual_hash,
        )
        cases.append(
            BenchmarkCase(
                target_id=target_id,
                accent=accent,
                actual_tone=actual_tone,
                path=path,
                file_sha256=actual_hash,
                model=REFERENCE_MODEL,
                prompt_sha256=PROMPT_SHA256,
                case_sha256=case_hash,
            )
        )
    return cases


def _corpus_receipt(manifest_path: Path, cases: Sequence[BenchmarkCase]) -> dict[str, Any]:
    case_facts = [
        {
            "target_id": case.target_id,
            "accent": case.accent,
            "tone": case.actual_tone,
            "file_sha256": case.file_sha256,
        }
        for case in sorted(cases, key=lambda item: (item.accent, item.target_id))
    ]
    return {
        "manifest_sha256": _sha256_file(manifest_path),
        "cases_sha256": _canonical_json_sha256(case_facts),
        "target_count": len(cases),
    }


def _audio_pcm24(path: Path) -> bytes:
    samples, rate = sf.read(path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)
    if rate != 24_000:
        divisor = np.gcd(rate, 24_000)
        samples = resample_poly(samples, 24_000 // divisor, rate // divisor)
    return cast(bytes, (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def _ask(path: Path) -> tuple[str, dict[str, Any]]:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for an uncached benchmark")
    deltas: list[str] = []
    usage: dict[str, Any] = {}
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
                        "instructions": BENCHMARK_PROMPT,
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


def _result_for_case(
    case: BenchmarkCase,
    raw_answer: str,
    usage: Mapping[str, Any] | None,
) -> dict[str, Any]:
    predicted = _normalize_answer(raw_answer)
    return {
        "target_id": case.target_id,
        "accent": case.accent,
        "model": case.model,
        "file_sha256": case.file_sha256,
        "prompt_sha256": case.prompt_sha256,
        "case_sha256": case.case_sha256,
        "actual_tone": case.actual_tone,
        "raw_answer": raw_answer,
        "predicted_tone": predicted,
        "exact_correct": predicted == case.actual_tone,
        "family_correct": bool(
            predicted
            and tone_family(predicted, case.accent)
            == tone_family(case.actual_tone, case.accent)
        ),
        "usage": dict(usage or {}),
    }


def _validated_cached_result(
    case: BenchmarkCase,
    cached: Mapping[str, Any],
) -> dict[str, Any] | None:
    expected = {
        "target_id": case.target_id,
        "accent": case.accent,
        "model": case.model,
        "file_sha256": case.file_sha256,
        "prompt_sha256": case.prompt_sha256,
        "case_sha256": case.case_sha256,
        "actual_tone": case.actual_tone,
    }
    if any(cached.get(key) != value for key, value in expected.items()):
        return None
    raw_answer = cached.get("raw_answer")
    if not isinstance(raw_answer, str):
        return None
    usage = cached.get("usage")
    return _result_for_case(
        case,
        raw_answer,
        usage if isinstance(usage, Mapping) else {},
    )


def _cache_index(
    cases: Sequence[BenchmarkCase],
    cached_payload: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    raw_results = cached_payload.get("results", [])
    if not isinstance(raw_results, list):
        return {}
    by_case: dict[str, Mapping[str, Any]] = {}
    duplicate_hashes: set[str] = set()
    for item in raw_results:
        if not isinstance(item, Mapping):
            continue
        case_hash = item.get("case_sha256")
        if not isinstance(case_hash, str):
            continue
        if case_hash in by_case:
            duplicate_hashes.add(case_hash)
        else:
            by_case[case_hash] = item
    resolved: dict[str, dict[str, Any]] = {}
    for case in cases:
        if case.case_sha256 in duplicate_hashes:
            continue
        raw = by_case.get(case.case_sha256)
        if raw is None:
            continue
        validated = _validated_cached_result(case, raw)
        if validated is not None:
            resolved[case.case_sha256] = validated
    return resolved


def _summary(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for accent in ("north", "south", "all"):
        rows = (
            list(results)
            if accent == "all"
            else [row for row in results if row["accent"] == accent]
        )
        summary[accent] = {
            "samples": len(rows),
            "exact_accuracy": (
                sum(bool(row["exact_correct"]) for row in rows) / len(rows) if rows else 0.0
            ),
            "family_accuracy": (
                sum(bool(row["family_correct"]) for row in rows) / len(rows) if rows else 0.0
            ),
            "predictions": dict(Counter(row.get("predicted_tone") or "invalid" for row in rows)),
        }
    return summary


def comparison_rows(
    dsp_report: Mapping[str, Any],
    benchmark_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Return comparable per-accent rows only for matching complete receipts."""

    if benchmark_report.get("complete") is not True:
        return []
    dsp_corpus = dsp_report.get("corpus")
    benchmark_corpus = benchmark_report.get("corpus")
    if not isinstance(dsp_corpus, Mapping) or not isinstance(benchmark_corpus, Mapping):
        return []
    if (
        dsp_corpus.get("cases_sha256") != benchmark_corpus.get("cases_sha256")
        or dsp_corpus.get("target_count") != benchmark_corpus.get("target_count")
    ):
        return []
    accents = dsp_report.get("accents")
    benchmark_summary = benchmark_report.get("summary")
    if not isinstance(accents, Mapping) or not isinstance(benchmark_summary, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for accent in ("north", "south"):
        dsp_accent = accents.get(accent)
        model_accent = benchmark_summary.get(accent)
        if not isinstance(dsp_accent, Mapping) or not isinstance(model_accent, Mapping):
            return []
        selected = dsp_accent.get("selected")
        if not isinstance(selected, Mapping) or not isinstance(selected.get("metrics"), Mapping):
            return []
        metrics = selected["metrics"]
        mode = str(dsp_accent.get("scoring_mode", ""))
        exact = mode in {"six-tone", "six_tone"}
        model_metric = "exact_accuracy" if exact else "family_accuracy"
        if model_metric not in model_accent:
            return []
        rows.append(
            {
                "accent": accent,
                "scoring_basis": "six tones" if exact else "four acoustic families",
                "dsp_covered_accuracy": float(metrics.get("accuracy", 0.0)),
                "dsp_coverage": float(metrics.get("coverage", 0.0)),
                "audio_model_accuracy": float(model_accent[model_metric]),
                "dsp_samples": int(metrics.get("samples", 0)),
                "audio_model_samples": int(model_accent.get("samples", 0)),
            }
        )
    return rows


def render_comparison(rows: Sequence[Mapping[str, Any]], *, model: str) -> str:
    if not rows:
        return ""
    lines = [
        "DSP vs. audio-model tone grading",
        "",
        f"| Accent | Shared scoring basis | DSP accuracy (coverage) | {model} accuracy | Samples |",
        "| :-- | :-- | --: | --: | --: |",
    ]
    for row in rows:
        lines.append(
            f"| {str(row['accent']).title()} | {row['scoring_basis']} | "
            f"{float(row['dsp_covered_accuracy']):.1%} "
            f"({float(row['dsp_coverage']):.1%}) | "
            f"{float(row['audio_model_accuracy']):.1%} | "
            f"{int(row['audio_model_samples'])} |"
        )
    return "\n".join(lines)


def _compose_output(
    cases: Sequence[BenchmarkCase],
    result_index: Mapping[str, Mapping[str, Any]],
    *,
    corpus: Mapping[str, Any],
    evaluation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    results = [
        dict(result_index[case.case_sha256])
        for case in cases
        if case.case_sha256 in result_index
    ]
    missing = [
        {"target_id": case.target_id, "accent": case.accent}
        for case in cases
        if case.case_sha256 not in result_index
    ]
    output: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "model": REFERENCE_MODEL,
        "prompt_sha256": PROMPT_SHA256,
        "method": "closed-set tone naming over DSP-validated sibling-model targets",
        "corpus": dict(corpus),
        "complete": not missing,
        "evaluated_targets": len(results),
        "missing_targets": missing,
        "summary": _summary(results),
        "results": results,
    }
    if evaluation is not None:
        rows = comparison_rows(evaluation, output)
        if rows:
            output["comparison"] = {"status": "ready", "rows": rows}
        elif output["complete"]:
            output["comparison"] = {
                "status": "withheld",
                "reason": "DSP and audio-model corpus receipts do not match",
            }
    return output


def run_benchmark(
    cases: Sequence[BenchmarkCase],
    cached_payload: Mapping[str, Any],
    *,
    corpus: Mapping[str, Any],
    evaluation: Mapping[str, Any] | None = None,
    request_limit: int = 0,
    ask: Callable[[Path], tuple[str, dict[str, Any]]] | None = None,
    on_result: Callable[[BenchmarkCase, Mapping[str, Any]], None] | None = None,
    persist: Callable[[Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Fill only valid cache misses; ``request_limit`` caps new live calls."""

    if request_limit < 0:
        raise ValueError("request_limit cannot be negative")
    result_index = _cache_index(cases, cached_payload)
    pending = [case for case in cases if case.case_sha256 not in result_index]
    selected = pending[:request_limit] if request_limit else pending
    ask_fn = ask or _ask
    for case in selected:
        raw_answer, usage = ask_fn(case.path)
        result = _result_for_case(case, raw_answer, usage)
        result_index[case.case_sha256] = result
        if on_result is not None:
            on_result(case, result)
        if persist is not None:
            persist(
                _compose_output(
                    cases,
                    result_index,
                    corpus=corpus,
                    evaluation=evaluation,
                )
            )
    return _compose_output(
        cases,
        result_index,
        corpus=corpus,
        evaluation=evaluation,
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return value


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="maximum number of uncached live calls; 0 runs every cache miss",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit cannot be negative")
    if not reference_corpus_is_complete():
        raise RuntimeError(
            "The audio-model benchmark requires the complete validated target manifest."
        )
    manifest = target_manifest()
    cases = _benchmark_cases(manifest)
    corpus = _corpus_receipt(MANIFEST_PATH, cases)
    cached = _load_json_object(OUTPUT_PATH)
    evaluation = _load_json_object(EVALUATION_PATH) if EVALUATION_PATH.exists() else None
    cached_index = _cache_index(cases, cached)
    pending = [case for case in cases if case.case_sha256 not in cached_index]
    selected = pending[: args.limit] if args.limit else pending
    if selected:
        approve(
            len(selected) * ESTIMATED_REQUEST_USD,
            f"audio-model benchmark ({len(selected)} files)",
        )

    def report_result(case: BenchmarkCase, result: Mapping[str, Any]) -> None:
        record(
            f"benchmark:{case.accent}:{case.target_id}",
            ESTIMATED_REQUEST_USD,
            dict(result.get("usage", {})),
        )
        print(
            f"{case.accent}/{case.target_id}: {case.actual_tone} -> "
            f"{result.get('predicted_tone') or 'invalid'} "
            f"({'correct' if result['exact_correct'] else 'wrong'})"
        )

    output = run_benchmark(
        cases,
        cached,
        corpus=corpus,
        evaluation=evaluation,
        request_limit=args.limit,
        on_result=report_result,
        persist=lambda value: _atomic_write_json(OUTPUT_PATH, value),
    )
    _atomic_write_json(OUTPUT_PATH, output)
    print(json.dumps(output["summary"], indent=2))
    comparison = output.get("comparison")
    if isinstance(comparison, Mapping) and comparison.get("status") == "ready":
        rendered = render_comparison(comparison.get("rows", []), model=REFERENCE_MODEL)
        if rendered:
            print(f"\n{rendered}")


if __name__ == "__main__":
    main()
