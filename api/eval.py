"""Leakage-safe evaluation for the committed Dấu reference corpus.

Run from the repository root:

    python -m api.eval

The evaluator never trains on another accent's take or on another take of the
held-out word. Results describe synthetic reference audio, not learner accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dau.tones import (
    FAMILY_ORDER,
    TONE_LABELS,
    TONE_ORDER,
    Accent,
    ContourFeatures,
    ScoringMode,
    Tone,
    ToneTemplate,
    analyze_audio,
    canonical_accent,
    canonical_tone,
    classify_contour,
    contour_from_points,
    extract_features,
    resample_contour,
    tone_family,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "targets" / "manifest.json"
DEFAULT_JSON = ROOT / "api" / "data" / "evaluation.json"
DEFAULT_MARKDOWN = ROOT / "api" / "data" / "evaluation.md"
DEFAULT_FIGURE = ROOT / "web" / "public" / "figures" / "six-tone-contours.png"


@dataclass(frozen=True)
class FoldPrediction:
    target_id: str
    word: str
    accent: str
    actual_tone: str
    predicted_tone: str
    actual_label: str
    predicted_label: str
    confidence: float
    needs_retry: bool
    temperature: float
    abstention_threshold: float


def _iter_manifest_entries(value: Any) -> Iterable[Mapping[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_manifest_entries(item)
        return
    if not isinstance(value, Mapping):
        return
    has_identity = "tone" in value and any(
        key in value
        for key in (
            "audio",
            "audio_path",
            "file",
            "filename",
            "path",
            "contour",
            "normalized_contour",
        )
    )
    if has_identity:
        yield value
        return
    for key in ("targets", "entries", "items", "references", "profiles", "accents"):
        if key in value:
            yield from _iter_manifest_entries(value[key])


def _entry_path(entry: Mapping[str, Any], manifest_path: Path) -> Path | None:
    raw = next(
        (
            entry.get(key)
            for key in ("audio_path", "audio", "path", "file", "filename")
            if entry.get(key)
        ),
        None,
    )
    if raw is None:
        return None
    path = Path(str(raw))
    if path.is_absolute():
        return path
    candidates = (
        ROOT / path,
        manifest_path.parent / path,
        manifest_path.parent / "audio" / path,
    )
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _entry_contour(entry: Mapping[str, Any]) -> np.ndarray | None:
    raw = entry.get("normalized_contour", entry.get("contour"))
    if isinstance(raw, Mapping):
        raw = raw.get("points", raw.get("values"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        analysis = entry.get("analysis")
        if isinstance(analysis, Mapping):
            raw = analysis.get("normalized_contour", analysis.get("contour"))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    return resample_contour(np.asarray(raw, dtype=np.float64))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _word_group(word: str) -> str:
    """Return the NFC/case-insensitive group key used by every fold."""

    return unicodedata.normalize("NFC", word).casefold().strip()


def _fold_training_set(
    templates: Sequence[ToneTemplate],
    held_out: ToneTemplate,
    accent: Accent,
) -> list[ToneTemplate]:
    """Exclude the full lexical group and every other accent from a fold."""

    held_out_group = _word_group(held_out.word)
    return [
        template
        for template in templates
        if template.accent is accent and _word_group(template.word) != held_out_group
    ]


def load_templates(manifest_path: str | Path = DEFAULT_MANIFEST) -> list[ToneTemplate]:
    path = Path(manifest_path).resolve()
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    templates: list[ToneTemplate] = []
    for index, entry in enumerate(_iter_manifest_entries(payload)):
        if entry.get("selected") is False or entry.get("status") in {
            "rejected",
            "failed",
        }:
            continue
        tone = canonical_tone(str(entry["tone"]))
        accent = canonical_accent(str(entry.get("accent", entry.get("profile", "north"))))
        word = str(
            entry.get(
                "word",
                entry.get(
                    "surface", entry.get("syllable", entry.get("word_id", entry.get("text", "")))
                ),
            )
        )
        target_id = str(
            entry.get("id", entry.get("target_id", entry.get("word_id", f"{accent.value}-{index}")))
        )
        source_path = _entry_path(entry, path)
        contour = _entry_contour(entry)
        feature_data = entry.get("features")
        if source_path is not None and source_path.exists():
            expected_hash = entry.get("sha256")
            actual_hash = _sha256_file(source_path)
            if expected_hash is not None and expected_hash != actual_hash:
                raise ValueError(
                    f"Manifest target {target_id!r} SHA-256 mismatch: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
            analyzed = analyze_audio(source_path)
            contour = analyzed.points
            features = analyzed.features
        elif isinstance(feature_data, Mapping):
            features = ContourFeatures.from_mapping(feature_data)
        elif contour is not None:
            features = extract_features(
                contour,
                duration_s=float(entry.get("duration_s", 0.5)),
                voiced_fraction=float(entry.get("voiced_fraction", 1.0)),
                longest_voicing_gap_ms=float(entry.get("longest_voicing_gap_ms", 0.0)),
            )
        else:
            raise ValueError(
                f"Manifest target {target_id!r} has neither a contour nor readable audio"
            )
        templates.append(
            ToneTemplate(
                id=target_id,
                word=word,
                tone=tone,
                accent=accent,
                contour=np.asarray(contour, dtype=np.float64),
                features=features,
                source_path=str(source_path) if source_path else None,
            )
        )
    if not templates:
        raise ValueError(f"No selected targets found in {path}")
    duplicate_ids = [
        item for item, count in Counter(template.id for template in templates).items() if count > 1
    ]
    if duplicate_ids:
        raise ValueError(f"Duplicate target IDs: {', '.join(sorted(duplicate_ids))}")
    return templates


def corpus_receipt(
    manifest_path: str | Path,
    templates: Sequence[ToneTemplate],
) -> dict[str, Any]:
    """Bind an evaluation report to the manifest and exact audio bytes it used."""

    path = Path(manifest_path).resolve()
    cases: list[dict[str, str]] = []
    for template in templates:
        if not template.source_path:
            raise ValueError(f"Evaluation target {template.id!r} has no source audio path")
        source_path = Path(template.source_path).resolve()
        if not source_path.is_file():
            raise ValueError(f"Evaluation target {template.id!r} audio is missing: {source_path}")
        cases.append(
            {
                "target_id": template.id,
                "accent": template.accent.value,
                "tone": template.tone.value,
                "file_sha256": _sha256_file(source_path),
            }
        )
    cases.sort(key=lambda item: (item["accent"], item["target_id"]))
    canonical_cases = json.dumps(
        cases,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return {
        "manifest_sha256": _sha256_file(path),
        "cases_sha256": hashlib.sha256(canonical_cases).hexdigest(),
        "target_count": len(cases),
    }


def _inner_scores(
    templates: Sequence[ToneTemplate],
    accent: Accent,
    mode: ScoringMode,
) -> list[tuple[bool, list[float]]]:
    predictions: list[tuple[bool, list[float]]] = []
    accent_templates = [template for template in templates if template.accent is accent]
    for held_out in accent_templates:
        training = _fold_training_set(accent_templates, held_out, accent)
        labels = {
            tone_family(template.tone, accent).value
            if mode is ScoringMode.FOUR_FAMILY
            else template.tone.value
            for template in training
        }
        expected = (
            tone_family(held_out.tone, accent).value
            if mode is ScoringMode.FOUR_FAMILY
            else held_out.tone.value
        )
        if expected not in labels:
            continue
        analysis = contour_from_points(
            held_out.contour,
            duration_s=held_out.features.duration_s,
            voiced_fraction=held_out.features.voiced_fraction,
            longest_voicing_gap_ms=held_out.features.longest_voicing_gap_ms,
            central_rms_dip=held_out.features.central_rms_dip,
            terminal_energy_drop=held_out.features.terminal_energy_drop,
        )
        result = classify_contour(
            analysis,
            training,
            accent=accent,
            scoring_mode=mode,
            temperature=1.0,
            abstention_threshold=0.0,
        )
        predicted = result.family.value if mode is ScoringMode.FOUR_FAMILY else result.tone.value
        predictions.append((predicted == expected, list(result.scores.values())))
    return predictions


def _winning_probability(scores: Sequence[float], temperature: float) -> float:
    values = -np.asarray(scores, dtype=np.float64) / max(temperature, 1e-6)
    values -= np.max(values)
    probabilities = np.exp(values)
    return min(0.95, float(np.max(probabilities) / np.sum(probabilities)))


def _calibrate_fold(
    training: Sequence[ToneTemplate],
    accent: Accent,
    mode: ScoringMode,
) -> tuple[float, float]:
    """Select confidence parameters using only the outer fold's training set."""

    temperatures = (0.20, 0.26, 0.32, 0.40, 0.50)
    best_temperature = 0.32
    best_brier = math.inf
    cached: dict[float, list[tuple[bool, float]]] = {}
    score_rows = _inner_scores(training, accent, mode)
    for temperature in temperatures:
        predictions = [
            (correct, _winning_probability(scores, temperature)) for correct, scores in score_rows
        ]
        cached[temperature] = predictions
        if not predictions:
            continue
        brier = float(
            np.mean([(confidence - float(correct)) ** 2 for correct, confidence in predictions])
        )
        if brier < best_brier:
            best_brier = brier
            best_temperature = temperature

    predictions = cached.get(best_temperature, [])
    best_threshold = 0.43
    best_utility = -math.inf
    for threshold in (0.30, 0.36, 0.42, 0.48, 0.54):
        covered = [
            (correct, confidence) for correct, confidence in predictions if confidence >= threshold
        ]
        coverage = len(covered) / len(predictions) if predictions else 0.0
        if coverage < 0.70 or not covered:
            continue
        accuracy = sum(correct for correct, _ in covered) / len(covered)
        utility = accuracy - 0.10 * (1.0 - coverage)
        if utility > best_utility:
            best_utility = utility
            best_threshold = threshold
    return best_temperature, best_threshold


def grouped_leave_one_word_out(
    templates: Sequence[ToneTemplate],
    accent: Accent | str,
    mode: ScoringMode | str,
) -> list[FoldPrediction]:
    resolved_accent = canonical_accent(accent)
    resolved_mode = ScoringMode(mode)
    accent_templates = [template for template in templates if template.accent is resolved_accent]
    predictions: list[FoldPrediction] = []
    for held_out in accent_templates:
        training = _fold_training_set(accent_templates, held_out, resolved_accent)
        if not training:
            continue
        expected_label = (
            tone_family(held_out.tone, resolved_accent).value
            if resolved_mode is ScoringMode.FOUR_FAMILY
            else held_out.tone.value
        )
        training_labels = {
            tone_family(template.tone, resolved_accent).value
            if resolved_mode is ScoringMode.FOUR_FAMILY
            else template.tone.value
            for template in training
        }
        if expected_label not in training_labels:
            continue
        temperature, abstention = _calibrate_fold(training, resolved_accent, resolved_mode)
        analysis = contour_from_points(
            held_out.contour,
            duration_s=held_out.features.duration_s,
            voiced_fraction=held_out.features.voiced_fraction,
            longest_voicing_gap_ms=held_out.features.longest_voicing_gap_ms,
            central_rms_dip=held_out.features.central_rms_dip,
            terminal_energy_drop=held_out.features.terminal_energy_drop,
        )
        result = classify_contour(
            analysis,
            training,
            accent=resolved_accent,
            scoring_mode=resolved_mode,
            temperature=temperature,
            abstention_threshold=abstention,
        )
        predicted_label = (
            result.family.value if resolved_mode is ScoringMode.FOUR_FAMILY else result.tone.value
        )
        predictions.append(
            FoldPrediction(
                target_id=held_out.id,
                word=held_out.word,
                accent=resolved_accent.value,
                actual_tone=held_out.tone.value,
                predicted_tone=result.tone.value,
                actual_label=expected_label,
                predicted_label=predicted_label,
                confidence=result.confidence,
                needs_retry=result.needs_retry,
                temperature=temperature,
                abstention_threshold=abstention,
            )
        )
    return predictions


def confusion_matrix(
    predictions: Sequence[FoldPrediction],
    labels: Sequence[str],
    *,
    include_abstentions: bool = False,
) -> list[list[int]]:
    index = {label: position for position, label in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for prediction in predictions:
        if prediction.needs_retry and not include_abstentions:
            continue
        if prediction.actual_label in index and prediction.predicted_label in index:
            matrix[index[prediction.actual_label]][index[prediction.predicted_label]] += 1
    return matrix


def _metrics(predictions: Sequence[FoldPrediction], labels: Sequence[str]) -> dict[str, Any]:
    total = len(predictions)
    covered = [prediction for prediction in predictions if not prediction.needs_retry]
    correct = [
        prediction
        for prediction in covered
        if prediction.actual_label == prediction.predicted_label
    ]
    per_label: dict[str, dict[str, float | int]] = {}
    recalls: list[float] = []
    for label in labels:
        actual = [prediction for prediction in covered if prediction.actual_label == label]
        label_correct = [prediction for prediction in actual if prediction.predicted_label == label]
        recall = len(label_correct) / len(actual) if actual else 0.0
        recalls.append(recall)
        per_label[label] = {"support": len(actual), "recall": round(recall, 6)}
    return {
        "samples": total,
        "covered": len(covered),
        "coverage": round(len(covered) / total, 6) if total else 0.0,
        "accuracy": round(len(correct) / len(covered), 6) if covered else 0.0,
        "macro_recall": round(float(np.mean(recalls)), 6) if recalls else 0.0,
        "per_label": per_label,
    }


def _northern_six_tone_passes(
    predictions: Sequence[FoldPrediction],
    metrics: Mapping[str, Any],
) -> tuple[bool, dict[str, float]]:
    hoi_nga = [
        prediction
        for prediction in predictions
        if not prediction.needs_retry
        and prediction.actual_label in {Tone.HOI.value, Tone.NGA.value}
    ]
    mutual = [
        prediction
        for prediction in hoi_nga
        if {prediction.actual_label, prediction.predicted_label} == {Tone.HOI.value, Tone.NGA.value}
    ]
    mutual_rate = len(mutual) / len(hoi_nga) if hoi_nga else 1.0
    tone_recalls = [float(metrics["per_label"][tone.value]["recall"]) for tone in TONE_ORDER]
    distinct_words = [
        len(
            {
                prediction.word.casefold()
                for prediction in predictions
                if prediction.actual_label == tone.value
            }
        )
        for tone in TONE_ORDER
    ]
    checks = {
        "accuracy": float(metrics["accuracy"]),
        "macro_recall": float(metrics["macro_recall"]),
        "minimum_tone_recall": min(tone_recalls, default=0.0),
        "hoi_nga_mutual_confusion": mutual_rate,
        "minimum_distinct_words_per_tone": float(min(distinct_words, default=0)),
    }
    passed = (
        checks["accuracy"] >= 0.80
        and checks["macro_recall"] >= 0.75
        and checks["minimum_tone_recall"] >= 0.60
        and checks["hoi_nga_mutual_confusion"] <= 0.20
        and checks["minimum_distinct_words_per_tone"] >= 3
    )
    return passed, {key: round(value, 6) for key, value in checks.items()}


def evaluate(
    templates: Sequence[ToneTemplate],
    *,
    receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "method": "grouped leave-one-word-out over synthetic references",
        "warning": (
            "These metrics measure held-out synthetic reference audio, not "
            "learner-population accuracy."
        ),
        "accents": {},
    }
    if receipt is not None:
        report["corpus"] = dict(receipt)
    for accent in (Accent.NORTH, Accent.SOUTH):
        exact_predictions = grouped_leave_one_word_out(templates, accent, ScoringMode.SIX_TONE)
        exact_labels = [tone.value for tone in TONE_ORDER]
        exact_metrics = _metrics(exact_predictions, exact_labels)
        gate: dict[str, float | str]
        if accent is Accent.NORTH:
            six_tone_passed, northern_gate = _northern_six_tone_passes(
                exact_predictions, exact_metrics
            )
            gate = dict(northern_gate)
            selected_mode = ScoringMode.SIX_TONE if six_tone_passed else ScoringMode.FOUR_FAMILY
        else:
            selected_mode = ScoringMode.FOUR_FAMILY
            gate = {
                "forced_four_family": 1.0,
                "reason": "Common Southern hỏi/ngã merger",
            }
        if selected_mode is ScoringMode.SIX_TONE:
            selected_predictions = exact_predictions
            selected_labels = exact_labels
        else:
            selected_predictions = grouped_leave_one_word_out(
                templates, accent, ScoringMode.FOUR_FAMILY
            )
            selected_labels = [family.value for family in FAMILY_ORDER]
        report["accents"][accent.value] = {
            "scoring_mode": selected_mode.value,
            "mode_gate": gate,
            "exact_six_tone": {
                "labels": exact_labels,
                "matrix": confusion_matrix(exact_predictions, exact_labels),
                "metrics": exact_metrics,
            },
            "selected": {
                "labels": selected_labels,
                "matrix": confusion_matrix(selected_predictions, selected_labels),
                "metrics": _metrics(selected_predictions, selected_labels),
            },
            "folds": [asdict(prediction) for prediction in selected_predictions],
        }
    return report


def _markdown_matrix(labels: Sequence[str], matrix: Sequence[Sequence[int]]) -> list[str]:
    display = [
        TONE_LABELS.get(Tone(label), label)
        if label in {tone.value for tone in TONE_ORDER}
        else label
        for label in labels
    ]
    rows = ["| actual \\ predicted | " + " | ".join(display) + " |"]
    rows.append("| :-- | " + " | ".join(":--:" for _ in labels) + " |")
    for label, values in zip(display, matrix, strict=True):
        rows.append(f"| {label} | " + " | ".join(str(value) for value in values) + " |")
    return rows


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Dấu DSP evaluation",
        "",
        (
            "> Synthetic-reference grouped leave-one-word-out evaluation. This is not a "
            "claim about learner-population accuracy."
        ),
        "",
    ]
    for accent in (Accent.NORTH, Accent.SOUTH):
        result = report["accents"][accent.value]
        selected = result["selected"]
        metrics = selected["metrics"]
        lines.extend(
            (
                f"## {accent.value.title()}",
                "",
                f"Scoring mode: **{result['scoring_mode']}**  ",
                f"Covered accuracy: **{metrics['accuracy']:.1%}**  ",
                f"Macro recall: **{metrics['macro_recall']:.1%}**  ",
                f"Coverage: **{metrics['coverage']:.1%}**",
                "",
            )
        )
        lines.extend(_markdown_matrix(selected["labels"], selected["matrix"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_contour_figure(templates: Sequence[ToneTemplate], output_path: str | Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False
    colors = {
        Tone.NGANG: "#d8c39b",
        Tone.HUYEN: "#4c83c3",
        Tone.SAC: "#ff675f",
        Tone.HOI: "#9a74e8",
        Tone.NGA: "#41c7b2",
        Tone.NANG: "#e9a43a",
    }
    figure, axis = plt.subplots(figsize=(10, 5.6), dpi=180)
    figure.patch.set_facecolor("#0e0d0c")
    axis.set_facecolor("#0e0d0c")
    x = np.linspace(0.0, 1.0, 64)
    preferred = [template for template in templates if template.accent is Accent.NORTH]
    for tone in TONE_ORDER:
        members = [template.contour for template in preferred if template.tone is tone]
        if not members:
            members = [template.contour for template in templates if template.tone is tone]
        if not members:
            continue
        average = np.median(np.vstack(members), axis=0)
        axis.plot(x, average, color=colors[tone], linewidth=3.0, label=TONE_LABELS[tone])
    axis.grid(color="#ffffff", alpha=0.075, linewidth=0.7)
    axis.set_xlabel("syllable time", color="#a49d93")
    axis.set_ylabel("relative pitch (semitones)", color="#a49d93")
    axis.tick_params(colors="#807970")
    for spine in axis.spines.values():
        spine.set_visible(False)
    legend = axis.legend(frameon=False, ncol=3, loc="upper left")
    for text in legend.get_texts():
        text.set_color("#e8e1d6")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(output, facecolor=figure.get_facecolor(), bbox_inches="tight")
    plt.close(figure)
    return True


def write_outputs(
    report: Mapping[str, Any],
    templates: Sequence[ToneTemplate],
    *,
    json_path: str | Path = DEFAULT_JSON,
    markdown_path: str | Path = DEFAULT_MARKDOWN,
    figure_path: str | Path = DEFAULT_FIGURE,
) -> None:
    json_output = Path(json_path)
    markdown_output = Path(markdown_path)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    render_contour_figure(templates, figure_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    arguments = parser.parse_args()
    if not arguments.manifest.is_file():
        generation_report = ROOT / "targets" / "generation-report.json"
        missing: list[str] = []
        if generation_report.is_file():
            payload = json.loads(generation_report.read_text(encoding="utf-8"))
            missing = [str(item["pair_id"]) for item in payload.get("failures", [])]
        detail = f" Missing validated pairs: {', '.join(missing)}." if missing else ""
        parser.error(
            "The final target manifest is withheld until every reference passes validation."
            f"{detail} Import the phone fallbacks with api/scripts/import_phone_targets.py, "
            "then rerun this command."
        )
    templates = load_templates(arguments.manifest)
    receipt = corpus_receipt(arguments.manifest, templates)
    report = evaluate(templates, receipt=receipt)
    write_outputs(
        report,
        templates,
        json_path=arguments.json,
        markdown_path=arguments.markdown,
        figure_path=arguments.figure,
    )
    print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
