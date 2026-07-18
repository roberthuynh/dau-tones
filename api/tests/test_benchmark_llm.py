from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import eval as evaluation
from dau.tones import Accent, Tone, ToneTemplate, contour_from_points, expected_tone_contour
from scripts import benchmark_llm


def _target(
    root: Path,
    target_id: str,
    accent: str,
    tone: str,
    payload: bytes,
) -> dict[str, object]:
    relative = Path("targets") / accent / f"{target_id}.wav"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "word_id": target_id,
        "accent": accent,
        "tone": tone,
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "validation": {"passed": True},
    }


def _receipt(cases: list[benchmark_llm.BenchmarkCase]) -> dict[str, object]:
    return {
        "manifest_sha256": "a" * 64,
        "cases_sha256": "b" * 64,
        "target_count": len(cases),
    }


def test_benchmark_cache_avoids_live_call_and_rescores_cached_answer(tmp_path: Path) -> None:
    manifest = {
        "targets": [_target(tmp_path, "ma-mother", "north", "sac", b"audio-one")]
    }
    cases = benchmark_llm._benchmark_cases(manifest, repo_root=tmp_path)
    cached_result = benchmark_llm._result_for_case(cases[0], "sắc", {"input_tokens": 7})
    cached_result["exact_correct"] = False
    cached = {"results": [cached_result]}

    def unexpected_live_call(_path: Path):
        raise AssertionError("a hash-valid cache entry must avoid a live call")

    output = benchmark_llm.run_benchmark(
        cases,
        cached,
        corpus=_receipt(cases),
        ask=unexpected_live_call,
    )

    assert output["complete"] is True
    assert output["evaluated_targets"] == 1
    assert output["results"][0]["exact_correct"] is True
    assert output["results"][0]["usage"] == {"input_tokens": 7}


def test_changed_audio_hash_invalidates_cache_without_network(tmp_path: Path) -> None:
    target = _target(tmp_path, "ma-ghost", "north", "ngang", b"first-audio")
    first_cases = benchmark_llm._benchmark_cases({"targets": [target]}, repo_root=tmp_path)
    cached = {
        "results": [benchmark_llm._result_for_case(first_cases[0], "ngang", {})]
    }

    target = _target(tmp_path, "ma-ghost", "north", "ngang", b"replacement-audio")
    second_cases = benchmark_llm._benchmark_cases({"targets": [target]}, repo_root=tmp_path)
    calls: list[Path] = []

    def local_answer(path: Path):
        calls.append(path)
        return "ngang", {"cached": False}

    output = benchmark_llm.run_benchmark(
        second_cases,
        cached,
        corpus=_receipt(second_cases),
        ask=local_answer,
    )

    assert calls == [second_cases[0].path]
    assert output["complete"] is True
    assert output["results"][0]["file_sha256"] != first_cases[0].file_sha256


def test_prompt_hash_mismatch_invalidates_cache(tmp_path: Path) -> None:
    manifest = {"targets": [_target(tmp_path, "ma-code", "south", "nga", b"audio")]}
    cases = benchmark_llm._benchmark_cases(manifest, repo_root=tmp_path)
    cached_result = benchmark_llm._result_for_case(cases[0], "ngã", {})
    cached_result["prompt_sha256"] = "0" * 64
    calls = 0

    def local_answer(_path: Path):
        nonlocal calls
        calls += 1
        return "hoi", {}

    output = benchmark_llm.run_benchmark(
        cases,
        {"results": [cached_result]},
        corpus=_receipt(cases),
        ask=local_answer,
    )

    assert calls == 1
    assert output["results"][0]["prompt_sha256"] == benchmark_llm.PROMPT_SHA256


def test_request_limit_preserves_an_honest_partial_receipt(tmp_path: Path) -> None:
    manifest = {
        "targets": [
            _target(tmp_path, "one", "north", "ngang", b"one"),
            _target(tmp_path, "two", "north", "sac", b"two"),
        ]
    }
    cases = benchmark_llm._benchmark_cases(manifest, repo_root=tmp_path)

    output = benchmark_llm.run_benchmark(
        cases,
        {},
        corpus=_receipt(cases),
        request_limit=1,
        ask=lambda _path: ("ngang", {}),
    )

    assert output["complete"] is False
    assert output["evaluated_targets"] == 1
    assert output["missing_targets"] == [{"target_id": "two", "accent": "north"}]
    assert output["summary"]["all"]["samples"] == 1


def test_manifest_file_hash_mismatch_stops_before_cache_or_live_calls(tmp_path: Path) -> None:
    target = _target(tmp_path, "ma-but", "north", "huyen", b"audio")
    target["sha256"] = "f" * 64

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        benchmark_llm._benchmark_cases({"targets": [target]}, repo_root=tmp_path)


def test_comparison_uses_each_dsp_receipts_selected_scoring_basis() -> None:
    corpus = {"cases_sha256": "c" * 64, "target_count": 38}
    dsp = {
        "corpus": corpus,
        "accents": {
            "north": {
                "scoring_mode": "six-tone",
                "selected": {"metrics": {"accuracy": 0.84, "coverage": 0.92, "samples": 19}},
            },
            "south": {
                "scoring_mode": "four-family",
                "selected": {"metrics": {"accuracy": 0.89, "coverage": 0.95, "samples": 19}},
            },
        },
    }
    benchmark = {
        "complete": True,
        "corpus": corpus,
        "summary": {
            "north": {"samples": 19, "exact_accuracy": 0.31, "family_accuracy": 0.47},
            "south": {"samples": 19, "exact_accuracy": 0.21, "family_accuracy": 0.42},
        },
    }

    rows = benchmark_llm.comparison_rows(dsp, benchmark)
    rendered = benchmark_llm.render_comparison(rows, model="gpt-realtime-2.1")

    assert rows[0]["audio_model_accuracy"] == 0.31
    assert rows[1]["audio_model_accuracy"] == 0.42
    assert "84.0% (92.0%)" in rendered
    assert "gpt-realtime-2.1 accuracy" in rendered


def test_comparison_is_withheld_for_mismatched_or_partial_receipts() -> None:
    dsp = {"corpus": {"cases_sha256": "a", "target_count": 38}, "accents": {}}
    mismatch = {
        "complete": True,
        "corpus": {"cases_sha256": "b", "target_count": 38},
    }
    partial = {
        "complete": False,
        "corpus": {"cases_sha256": "a", "target_count": 38},
    }

    assert benchmark_llm.comparison_rows(dsp, mismatch) == []
    assert benchmark_llm.comparison_rows(dsp, partial) == []


def test_evaluator_and_benchmark_share_the_same_corpus_fingerprint(tmp_path: Path) -> None:
    target = _target(tmp_path, "ma-mother", "north", "sac", b"shared-audio")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"targets": [target]}), encoding="utf-8")
    cases = benchmark_llm._benchmark_cases({"targets": [target]}, repo_root=tmp_path)
    analysis = contour_from_points(expected_tone_contour(Tone.SAC))
    template = ToneTemplate(
        id="ma-mother",
        word="má",
        tone=Tone.SAC,
        accent=Accent.NORTH,
        contour=analysis.points,
        features=analysis.features,
        source_path=str(cases[0].path),
    )

    dsp_receipt = evaluation.corpus_receipt(manifest_path, [template])
    model_receipt = benchmark_llm._corpus_receipt(manifest_path, cases)

    assert dsp_receipt == model_receipt
