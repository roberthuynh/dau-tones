#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join, relative, resolve } from "node:path";

const DATA_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(DATA_DIR, "../../..");
const TARGETS_ROOT = join(REPO_ROOT, "targets");
const manifestPath = existsSync(join(TARGETS_ROOT, "manifest.json"))
  ? join(TARGETS_ROOT, "manifest.json")
  : join(TARGETS_ROOT, "generation-report.json");
const inventoryPath = join(REPO_ROOT, "api/data/inventory.json");
const evaluationPath = join(REPO_ROOT, "api/data/evaluation.json");
const outputPath = join(DATA_DIR, "classifier-profile.generated.json");
const apiOutputPath = join(REPO_ROOT, "api/data/classifier_profile.json");

const sourceBytes = readFileSync(manifestPath);
const document = JSON.parse(sourceBytes.toString("utf8"));
const inventory = JSON.parse(readFileSync(inventoryPath, "utf8"));
const evaluation = existsSync(evaluationPath)
  ? JSON.parse(readFileSync(evaluationPath, "utf8"))
  : {};

const sha256 = (bytes) => createHash("sha256").update(bytes).digest("hex");
const round = (value, digits = 6) => Number(Number(value).toFixed(digits));
const median = (values) => {
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2
    ? sorted[middle]
    : (sorted[middle - 1] + sorted[middle]) / 2;
};

const featureFields = [
  "start",
  "end",
  "slope",
  "curvature",
  "pitch_range",
  "minimum",
  "dip_position",
  "recovery",
  "final_rise",
  "duration_s",
];
const defaultScales = [1.5, 1.5, 3, 5, 2.5, 1.5, 0.25, 2, 3, 0.22];
const toneOrder = ["ngang", "huyen", "sac", "hoi", "nga", "nang"];

let analyzePcm;
try {
  ({ analyzePcm } = await import("../lib/dspCore.ts"));
} catch (error) {
  throw new Error(
    "Run this generator with `node --experimental-strip-types web/src/data/build-classifier-profile.mjs`.",
    { cause: error },
  );
}

const validated = [];
for (const target of document.targets ?? []) {
  const sourcePath = target.path ? join(REPO_ROOT, target.path) : null;
  if (!target.validation?.passed || !sourcePath || !existsSync(sourcePath)) continue;
  const actualHash = sha256(readFileSync(sourcePath));
  if (actualHash !== target.sha256) {
    throw new Error(`Hash mismatch for ${relative(REPO_ROOT, sourcePath)}`);
  }
  if (!Array.isArray(target.contour) || target.contour.length !== 64) {
    throw new Error(`Expected 64 contour points for ${target.word_id}/${target.accent}`);
  }
  validated.push(target);
}

const expected = inventory.words.flatMap((word) =>
  ["north", "south"].map((accent) => `${accent}/${word.id}`),
);
const present = new Set(validated.map((target) => `${target.accent}/${target.word_id}`));
const missingTargetIds = expected.filter((id) => !present.has(id));
const sourceHash = sha256(sourceBytes);
const corpusComplete = missingTargetIds.length === 0 && validated.length === expected.length;

function featureScales(templates) {
  if (templates.length < 3) return defaultScales;
  return featureFields.map((field, index) => {
    const values = templates.map((template) => Number(template.features[field] ?? 0));
    const center = median(values);
    const mad = median(values.map((value) => Math.abs(value - center))) * 1.4826;
    return round(Math.max(mad, defaultScales[index] * 0.35));
  });
}

function profileFor(accent) {
  const templates = validated
    .filter((target) => target.accent === accent)
    .sort((left, right) => {
      const toneDifference = toneOrder.indexOf(left.tone) - toneOrder.indexOf(right.tone);
      return toneDifference || left.word_id.localeCompare(right.word_id);
    })
    .map((target) => ({
      id: `${target.accent}/${target.word_id}`,
      word_id: target.word_id,
      tone: target.tone,
      accent: target.accent,
      contour: target.contour.map((value) => round(value, 5)),
      features: Object.fromEntries(
        Object.entries(target.features).map(([key, value]) => [key, round(value)]),
      ),
      validated: true,
      source_path: target.path,
    }));
  const evaluatedMode = evaluation.accents?.north?.scoring_mode;
  const scoringMode =
    accent === "north" && corpusComplete && ["six_tone", "six-tone"].includes(evaluatedMode)
      ? "six_tone"
      : "four_family";
  return {
    version: "dau-browser-dsp-2.0.0",
    manifest_hash: sourceHash,
    accent,
    scoring_mode: scoringMode,
    temperature: 0.32,
    abstention_threshold: 0.43,
    minimum_margin: 0.05,
    feature_scales: featureScales(templates),
    corpus_complete: corpusComplete,
    missing_target_ids: missingTargetIds.filter((id) => id.startsWith(`${accent}/`)),
    templates,
  };
}

function decodePcmWave(path) {
  const bytes = readFileSync(path);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (bytes.subarray(0, 4).toString("ascii") !== "RIFF") {
    throw new Error(`Only committed PCM WAV targets can calibrate the browser profile: ${path}`);
  }
  let offset = 12;
  let format = 0;
  let channels = 0;
  let sampleRate = 0;
  let bits = 0;
  let dataOffset = 0;
  let dataLength = 0;
  while (offset + 8 <= bytes.byteLength) {
    const id = bytes.subarray(offset, offset + 4).toString("ascii");
    const length = view.getUint32(offset + 4, true);
    if (id === "fmt ") {
      format = view.getUint16(offset + 8, true);
      channels = view.getUint16(offset + 10, true);
      sampleRate = view.getUint32(offset + 12, true);
      bits = view.getUint16(offset + 22, true);
    } else if (id === "data") {
      dataOffset = offset + 8;
      dataLength = length;
      break;
    }
    offset += 8 + length + (length % 2);
  }
  if (format !== 1 || bits !== 16 || channels < 1 || !dataOffset) {
    throw new Error(`Expected 16-bit PCM WAV target: ${path}`);
  }
  const frameBytes = channels * 2;
  const frameCount = Math.floor(dataLength / frameBytes);
  const samples = new Float32Array(frameCount);
  for (let frame = 0; frame < frameCount; frame += 1) {
    let sum = 0;
    for (let channel = 0; channel < channels; channel += 1) {
      sum += view.getInt16(dataOffset + frame * frameBytes + channel * 2, true) / 32_768;
    }
    samples[frame] = sum / channels;
  }
  return { samples, sampleRate };
}

function browserCalibratedProfile(accent) {
  const initial = profileFor(accent);
  const templates = initial.templates.map((template) => {
    const decoded = decodePcmWave(join(REPO_ROOT, template.source_path));
    const analysis = analyzePcm(decoded.samples, decoded.sampleRate, initial);
    return {
      ...template,
      contour: analysis.contour.map((value) => round(value, 5)),
      features: Object.fromEntries(
        Object.entries(analysis.features).map(([key, value]) => [key, round(value)]),
      ),
    };
  });
  return {
    ...initial,
    feature_scales: featureScales(templates),
    templates,
  };
}

const output = {
  schema_version: 1,
  engine: {
    pitch_extractor: "browser-yin-v2",
    contour_points: 64,
    constrained_dtw_weight: 0.65,
    robust_feature_weight: 0.35,
    close_pair_cue_weight: 0.2,
  },
  source: relative(REPO_ROOT, manifestPath),
  source_hash: sourceHash,
  corpus_complete: corpusComplete,
  missing_target_ids: missingTargetIds,
  profiles: {
    north: browserCalibratedProfile("north"),
    south: browserCalibratedProfile("south"),
  },
};

writeFileSync(outputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
writeFileSync(apiOutputPath, `${JSON.stringify(output, null, 2)}\n`, "utf8");
console.log(
  `Wrote ${relative(REPO_ROOT, outputPath)} and ${relative(REPO_ROOT, apiOutputPath)} with ${validated.length}/${expected.length} validated targets.`,
);
if (!corpusComplete) {
  console.log(`Still gated on: ${missingTargetIds.join(", ")}`);
}
