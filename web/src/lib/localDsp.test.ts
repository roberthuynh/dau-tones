/// <reference types="node" />

import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { staticClassifierProfile } from "../data/classifierProfile";
import { FALLBACK_PAYLOAD } from "../fallbackData";
import type {
  Accent,
  ClassifierProfile,
  ClassifierTemplate,
  ContourFeatures,
  ToneId,
} from "../types";
import {
  analyzePcm,
  classifyContour,
  constrainedDtwDistance,
  DspSignalError,
  extractContourFeatures,
  removeOctaveSpikes,
  toneFamily,
} from "./dspCore";
import { resolveClassifierProfile } from "./localDsp";

const line = (start: number, end: number) =>
  Array.from({ length: 64 }, (_, index) => start + ((end - start) * index) / 63);

const toneShapes: Record<ToneId, number[]> = {
  ngang: line(0.05, -0.05),
  huyen: line(1.6, -1.7),
  sac: Array.from({ length: 64 }, (_, index) => -1.6 + 4 * (index / 63) ** 1.7),
  hoi: Array.from({ length: 64 }, (_, index) => {
    const x = index / 63;
    return x < 0.58 ? 1.2 - 4.5 * x : -1.41 + 2.5 * ((x - 0.58) / 0.42);
  }),
  nga: Array.from({ length: 64 }, (_, index) => {
    const x = index / 63;
    return -1.3 + 3.8 * x + (x > 0.44 && x < 0.54 ? -0.65 : 0);
  }),
  nang: Array.from({ length: 64 }, (_, index) => 1.2 - 3.8 * Math.min(index / 44, 1)),
};

function syntheticFeatures(tone: ToneId): ContourFeatures {
  return extractContourFeatures(toneShapes[tone], {
    duration_s: tone === "nang" ? 0.25 : 0.62,
    voiced_fraction: tone === "nga" ? 0.74 : 0.94,
    longest_voicing_gap_ms: tone === "nga" ? 70 : 0,
    central_rms_dip: tone === "nga" ? 0.42 : 0.03,
    terminal_energy_drop: tone === "nang" ? 0.58 : 0.08,
  });
}

function syntheticProfile(accent: Accent): ClassifierProfile {
  const templates: ClassifierTemplate[] = Object.entries(toneShapes).map(([tone, contour]) => ({
    id: `${accent}/${tone}`,
    word_id: tone,
    tone: tone as ToneId,
    accent,
    contour,
    features: syntheticFeatures(tone as ToneId),
    validated: true,
  }));
  return {
    version: "test-profile",
    manifest_hash: "test-hash",
    accent,
    scoring_mode: "six_tone",
    temperature: 0.18,
    abstention_threshold: 0.3,
    minimum_margin: 0.02,
    feature_scales: [1.5, 1.5, 3, 5, 2.5, 1.5, 0.25, 2, 3, 0.22],
    corpus_complete: true,
    missing_target_ids: [],
    templates,
  };
}

function voicedSine(frequency: number, durationSeconds: number): Float32Array {
  const sampleRate = 11_025;
  const length = Math.floor(sampleRate * durationSeconds);
  return Float32Array.from({ length }, (_, index) => {
    const time = index / sampleRate;
    const fade = Math.min(1, time / 0.05, (durationSeconds - time) / 0.05);
    return 0.22 * Math.max(0, fade) * Math.sin(2 * Math.PI * frequency * time);
  });
}

function decodePcmWave(relativePath: string): { samples: Float32Array; sampleRate: number } {
  const bytes = readFileSync(
    resolve(dirname(fileURLToPath(import.meta.url)), "../../../", relativePath),
  );
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  expect(String.fromCharCode(...bytes.subarray(0, 4))).toBe("RIFF");
  let offset = 12;
  let format = 0;
  let channels = 0;
  let sampleRate = 0;
  let bits = 0;
  let dataOffset = 0;
  let dataLength = 0;
  while (offset + 8 <= bytes.byteLength) {
    const id = String.fromCharCode(...bytes.subarray(offset, offset + 4));
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
  expect(format).toBe(1);
  expect(bits).toBe(16);
  expect(channels).toBeGreaterThan(0);
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

describe("browser-local deterministic DSP", () => {
  it("ranks all six synthetic shapes without using the intended tone", () => {
    const profile = syntheticProfile("north");
    for (const tone of Object.keys(toneShapes) as ToneId[]) {
      const result = classifyContour(toneShapes[tone], syntheticFeatures(tone), 0.95, profile);
      expect(result.tone, tone).toBe(tone);
      expect(result.alternatives).toHaveLength(3);
      expect(result.classConfidence).toBeGreaterThan(0);
    }
  });

  it("keeps each accepted reference in its evaluated acoustic family", () => {
    for (const accent of ["north", "south"] as const) {
      const profile = {
        ...staticClassifierProfile(accent),
        scoring_mode: "six_tone" as const,
        abstention_threshold: 0,
        minimum_margin: 0,
      };
      expect(profile.templates).toHaveLength(17);
      for (const template of profile.templates) {
        const result = classifyContour(template.contour, template.features, 0.95, profile);
        expect(result.family, template.id).toBe(toneFamily(template.tone, accent));
        if (accent === "north") expect(result.tone, template.id).toBe(template.tone);
      }
    }
  });

  it("runs every hash-validated committed WAV through the browser extractor", () => {
    const rows: Array<{ expected: ToneId; detected: ToneId; accent: Accent }> = [];
    let retryCount = 0;
    for (const accent of ["north", "south"] as const) {
      const profile = staticClassifierProfile(accent);
      for (const template of profile.templates) {
        const decoded = decodePcmWave(template.source_path as string);
        let analysis;
        try {
          analysis = analyzePcm(decoded.samples, decoded.sampleRate, profile);
        } catch (error) {
          throw new Error(
            `${template.id}: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
        expect(analysis.contour, template.id).toHaveLength(64);
        expect(analysis.signalConfidence, template.id).toBeGreaterThan(0);
        if (analysis.classification.needsRetry) retryCount += 1;
        rows.push({ expected: template.tone, detected: analysis.classification.tone, accent });
      }
    }
    const exact = rows.filter((row) => row.expected === row.detected).length;
    const family = rows.filter(
      (row) => toneFamily(row.expected, row.accent) === toneFamily(row.detected, row.accent),
    ).length;
    expect(exact).toBe(34);
    expect(family).toBe(34);
    expect(retryCount).toBeLessThanOrEqual(2);
  });

  it("evaluates references without letting the held-out word become its own template", () => {
    const rows: Array<{ expected: ToneId; detected: ToneId; accent: Accent }> = [];
    let unavailableFolds = 0;
    for (const accent of ["north", "south"] as const) {
      const committed = staticClassifierProfile(accent);
      for (const heldOut of committed.templates) {
        const remaining = committed.templates.filter(
          (template) => template.word_id !== heldOut.word_id,
        );
        if (
          new Set(remaining.map((template) => template.tone)).size < 6
        ) {
          unavailableFolds += 1;
          continue;
        }
        const profile = {
          ...committed,
          scoring_mode: "six_tone" as const,
          abstention_threshold: 0,
          minimum_margin: 0,
          templates: remaining,
        };
        const result = classifyContour(
          heldOut.contour,
          heldOut.features,
          0.95,
          profile,
        );
        rows.push({ expected: heldOut.tone, detected: result.tone, accent });
      }
    }
    const exact = rows.filter((row) => row.expected === row.detected).length;
    const family = rows.filter(
      (row) => toneFamily(row.expected, row.accent) === toneFamily(row.detected, row.accent),
    ).length;
    expect(exact / rows.length).toBeGreaterThanOrEqual(0.69);
    expect(family / rows.length).toBeGreaterThanOrEqual(0.9);
    const corpusComplete =
      staticClassifierProfile("north").corpus_complete &&
      staticClassifierProfile("south").corpus_complete;
    if (corpusComplete) expect(unavailableFolds).toBe(0);
    else expect(unavailableFolds).toBeGreaterThan(0);
  });

  it("keeps six-tone grading gated until the four phone targets validate", () => {
    const north = resolveClassifierProfile(FALLBACK_PAYLOAD, "north");
    const south = resolveClassifierProfile(FALLBACK_PAYLOAD, "south");
    expect(north.corpus_complete).toBe(false);
    expect(south.corpus_complete).toBe(false);
    expect(north.scoring_mode).toBe("four_family");
    expect(south.scoring_mode).toBe("four_family");
    expect([...north.missing_target_ids, ...south.missing_target_ids].sort()).toEqual([
      "north/ma-grave",
      "north/pho-noodle-soup",
      "south/ma-grave",
      "south/phuong-phoenix",
    ]);
  });

  it("repairs isolated octave jumps before normalization", () => {
    const corrected = removeOctaveSpikes([100, 101, 200, 99, 100]);
    expect(corrected[2]).toBeCloseTo(100, 0);
  });

  it("uses constrained DTW to tolerate timing drift without erasing direction", () => {
    const reference = toneShapes.hoi;
    const delayedDip = Array.from({ length: 64 }, (_, index) => {
      const shifted = Math.max(0, index - 5);
      return reference[Math.min(reference.length - 1, shifted)];
    });
    expect(constrainedDtwDistance(reference, delayedDip)).toBeLessThan(
      constrainedDtwDistance(reference, toneShapes.sac),
    );
  });

  it("extracts a 64-point contour and reports signal quality separately", () => {
    const analysis = analyzePcm(voicedSine(145, 0.72), 11_025, syntheticProfile("north"));
    expect(analysis.contour).toHaveLength(64);
    expect(analysis.quality.voiced_fraction).toBeGreaterThan(0.5);
    expect(analysis.signalConfidence).toBeGreaterThan(0.35);
    expect(analysis.classification.classConfidence).toBeGreaterThan(0);
    expect(analysis.classification.tone).toBe("ngang");
  });

  it("rejects silence before making a tone or meaning assertion", () => {
    expect(() =>
      analyzePcm(new Float32Array(11_025), 11_025, syntheticProfile("north")),
    ).toThrowError(DspSignalError);
  });
});
