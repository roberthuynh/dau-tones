import type {
  Accent,
  ClassifierProfile,
  ContourFeatures,
  SignalQuality,
  ToneFamilyId,
  ToneId,
} from "../types";

export const DSP_SAMPLE_RATE = 11_025;
export const DSP_FRAME_SIZE = 1_024;
export const DSP_HOP_SIZE = 256;
export const DSP_CONTOUR_POINTS = 64;

const F0_MIN_HZ = 65;
const F0_MAX_HZ = 650;
const FEATURE_FIELDS = [
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
] as const satisfies ReadonlyArray<keyof ContourFeatures>;
const DEFAULT_FEATURE_SCALES = [1.5, 1.5, 3, 5, 2.5, 1.5, 0.25, 2, 3, 0.22];
const TONE_ORDER: ToneId[] = ["ngang", "huyen", "sac", "hoi", "nga", "nang"];
const FAMILY_ORDER: ToneFamilyId[] = ["level", "falling", "rising", "dipping"];

export class DspSignalError extends Error {
  readonly code: string;
  readonly details: Record<string, string | number>;

  constructor(code: string, message: string, details: Record<string, string | number> = {}) {
    super(message);
    this.name = "DspSignalError";
    this.code = code;
    this.details = details;
  }
}

export type DspToneAlternative = {
  tone: ToneId;
  family: ToneFamilyId;
  score: number;
  probability: number;
};

export type DspClassification = {
  tone: ToneId;
  family: ToneFamilyId;
  classConfidence: number;
  needsRetry: boolean;
  margin: number;
  alternatives: DspToneAlternative[];
  scores: Record<string, number>;
};

export type DspAnalysis = {
  contour: number[];
  features: ContourFeatures;
  quality: SignalQuality;
  signalConfidence: number;
  classification: DspClassification;
};

type SpeechSegment = {
  samples: Float32Array;
  quality: Omit<SignalQuality, "voiced_fraction" | "longest_voicing_gap_ms">;
};

const clamp = (value: number, minimum = 0, maximum = 1) =>
  Math.min(maximum, Math.max(minimum, value));

function finiteValues(values: Array<number | null>): number[] {
  return values.filter((value): value is number => value !== null && Number.isFinite(value));
}

export function percentile(values: number[], fraction: number): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const position = clamp(fraction) * (sorted.length - 1);
  const left = Math.floor(position);
  const mix = position - left;
  return sorted[left] * (1 - mix) + sorted[Math.min(sorted.length - 1, left + 1)] * mix;
}

function median(values: number[]): number {
  return percentile(values, 0.5);
}

export function resampleAudio(
  samples: Float32Array,
  sourceRate: number,
  targetRate = DSP_SAMPLE_RATE,
): Float32Array {
  if (sourceRate === targetRate) return samples;
  if (!Number.isFinite(sourceRate) || sourceRate <= 0) {
    throw new DspSignalError("decode_failed", "The recording had an invalid sample rate.");
  }
  const length = Math.max(1, Math.round((samples.length * targetRate) / sourceRate));
  const output = new Float32Array(length);
  const scale = (samples.length - 1) / Math.max(1, length - 1);
  for (let index = 0; index < length; index += 1) {
    const position = index * scale;
    const left = Math.floor(position);
    const mix = position - left;
    output[index] =
      samples[left] * (1 - mix) + samples[Math.min(samples.length - 1, left + 1)] * mix;
  }
  return output;
}

function frameRms(samples: Float32Array): number[] {
  if (!samples.length) return [];
  const levels: number[] = [];
  for (let start = 0; start + DSP_FRAME_SIZE <= samples.length; start += DSP_HOP_SIZE) {
    let sum = 0;
    for (let index = 0; index < DSP_FRAME_SIZE; index += 1) {
      const value = samples[start + index];
      sum += value * value;
    }
    levels.push(Math.sqrt(sum / DSP_FRAME_SIZE));
  }
  if (!levels.length) {
    let sum = 0;
    for (const value of samples) sum += value * value;
    levels.push(Math.sqrt(sum / Math.max(1, samples.length)));
  }
  return levels;
}

function fillShortFalseRuns(mask: boolean[], maximumFrames: number): boolean[] {
  const result = [...mask];
  let index = 0;
  while (index < result.length) {
    if (result[index]) {
      index += 1;
      continue;
    }
    let end = index;
    while (end < result.length && !result[end]) end += 1;
    if (index > 0 && end < result.length && end - index <= maximumFrames) {
      result.fill(true, index, end);
    }
    index = end;
  }
  return result;
}

function trueRuns(mask: boolean[]): Array<[number, number]> {
  const runs: Array<[number, number]> = [];
  let start: number | null = null;
  mask.forEach((active, index) => {
    if (active && start === null) start = index;
    if (!active && start !== null) {
      runs.push([start, index]);
      start = null;
    }
  });
  if (start !== null) runs.push([start, mask.length]);
  return runs;
}

function isolatePrimarySpeech(samples: Float32Array): SpeechSegment {
  if (!samples.length) {
    throw new DspSignalError("silence", "I could not hear a voice. Move closer and try again.");
  }
  let squareSum = 0;
  let peak = 0;
  let clippingCount = 0;
  for (const value of samples) {
    if (!Number.isFinite(value)) {
      throw new DspSignalError("nonfinite_audio", "The recording is damaged. Try recording again.");
    }
    squareSum += value * value;
    const absolute = Math.abs(value);
    peak = Math.max(peak, absolute);
    if (absolute >= 0.995) clippingCount += 1;
  }
  const rms = Math.sqrt(squareSum / samples.length);
  const clippingFraction = clippingCount / samples.length;
  if (rms < 0.0025 || peak < 0.01) {
    throw new DspSignalError(
      "silence",
      "I could not hear a clear word. Move closer and try again.",
      { rms, peak },
    );
  }
  if (clippingFraction > 0.02) {
    throw new DspSignalError(
      "clipped",
      "The recording is distorted. Move a little farther from the microphone.",
      { clipping_fraction: clippingFraction },
    );
  }

  const levels = frameRms(samples);
  const high = percentile(levels, 0.9);
  const quiet = percentile(levels, 0.2);
  let threshold = Math.max(0.003, high * 0.16);
  if (quiet < high * 0.35) threshold = Math.max(threshold, Math.min(high * 0.6, quiet * 2.5));
  const maximumGapFrames = Math.max(1, Math.round((0.08 * DSP_SAMPLE_RATE) / DSP_HOP_SIZE));
  const active = fillShortFalseRuns(
    levels.map((level) => level >= threshold),
    maximumGapFrames,
  );
  const minimumIslandFrames = Math.max(
    2,
    Math.round((0.06 * DSP_SAMPLE_RATE) / DSP_HOP_SIZE),
  );
  const runs = trueRuns(active).filter(([start, end]) => end - start >= minimumIslandFrames);
  if (!runs.length) {
    throw new DspSignalError("silence", "I could not find one clear syllable. Try recording again.");
  }
  const energies = runs.map(([start, end]) =>
    levels.slice(start, end).reduce((sum, level) => sum + level * level, 0),
  );
  const primaryIndex = energies.indexOf(Math.max(...energies));
  const substantial = runs.filter(
    ([start, end], index) =>
      ((end - start) * DSP_HOP_SIZE) / DSP_SAMPLE_RATE >= 0.12 &&
      energies[index] >= energies[primaryIndex] * 0.25,
  );
  if (substantial.length > 1) {
    throw new DspSignalError(
      "multiple_utterances",
      "Say one word at a time, with a short pause before and after.",
      { island_count: substantial.length },
    );
  }

  const [startFrame, endFrame] = runs[primaryIndex];
  const activeDuration = ((endFrame - startFrame) * DSP_HOP_SIZE) / DSP_SAMPLE_RATE;
  if (activeDuration < 0.12) {
    throw new DspSignalError(
      "too_short",
      "That was too short to grade. Hold the vowel for one comfortable beat.",
      { active_duration_s: activeDuration },
    );
  }
  if (activeDuration > 2.5) {
    throw new DspSignalError(
      "too_long",
      "Say just the target word, not a full phrase.",
      { active_duration_s: activeDuration },
    );
  }
  const padding = Math.round(0.05 * DSP_SAMPLE_RATE);
  const start = Math.max(0, startFrame * DSP_HOP_SIZE - padding);
  const end = Math.min(
    samples.length,
    endFrame * DSP_HOP_SIZE + DSP_FRAME_SIZE + padding,
  );
  return {
    samples: samples.slice(start, end),
    quality: {
      peak,
      rms,
      clipping_fraction: clippingFraction,
      active_duration_s: activeDuration,
      total_duration_s: samples.length / DSP_SAMPLE_RATE,
      island_count: substantial.length,
    },
  };
}

function yinPitch(frame: Float32Array): { f0: number; confidence: number } | null {
  let mean = 0;
  for (const value of frame) mean += value;
  mean /= frame.length;
  const minLag = Math.max(2, Math.floor(DSP_SAMPLE_RATE / F0_MAX_HZ));
  const maxLag = Math.min(frame.length - 2, Math.ceil(DSP_SAMPLE_RATE / F0_MIN_HZ));
  const difference = new Float64Array(maxLag + 1);
  for (let lag = 1; lag <= maxLag; lag += 1) {
    let sum = 0;
    const limit = frame.length - lag;
    for (let index = 0; index < limit; index += 1) {
      const delta = frame[index] - mean - (frame[index + lag] - mean);
      sum += delta * delta;
    }
    difference[lag] = sum;
  }
  const normalized = new Float64Array(maxLag + 1);
  normalized[0] = 1;
  let running = 0;
  for (let lag = 1; lag <= maxLag; lag += 1) {
    running += difference[lag];
    normalized[lag] = running > 0 ? (difference[lag] * lag) / running : 1;
  }
  let selected = -1;
  for (let lag = minLag; lag < maxLag; lag += 1) {
    if (
      normalized[lag] < 0.22 &&
      normalized[lag] <= normalized[lag - 1] &&
      normalized[lag] <= normalized[lag + 1]
    ) {
      selected = lag;
      break;
    }
  }
  if (selected < 0) {
    selected = minLag;
    for (let lag = minLag + 1; lag <= maxLag; lag += 1) {
      if (normalized[lag] < normalized[selected]) selected = lag;
    }
  }
  const confidence = 1 - normalized[selected];
  // Short, breathy Vietnamese rises often have a less periodic onset than a
  // sustained laboratory vowel. Energy and contour continuity provide the
  // second guard, so keep YIN frames down to this conservative floor.
  if (confidence < 0.3) return null;
  const left = normalized[Math.max(minLag, selected - 1)];
  const center = normalized[selected];
  const right = normalized[Math.min(maxLag, selected + 1)];
  const denominator = left - 2 * center + right;
  const correction = Math.abs(denominator) > 1e-9 ? 0.5 * (left - right) / denominator : 0;
  const refinedLag = selected + clamp(correction, -0.5, 0.5);
  return { f0: DSP_SAMPLE_RATE / refinedLag, confidence };
}

export function removeOctaveSpikes(values: Array<number | null>): Array<number | null> {
  const output = [...values];
  const validIndices = output.flatMap((value, index) =>
    value !== null && Number.isFinite(value) && value > 0 ? [index] : [],
  );
  if (validIndices.length < 3) return output;
  const semitones = validIndices.map((index) => 12 * Math.log2(output[index] as number));
  for (let position = 1; position < validIndices.length - 1; position += 1) {
    const local = semitones.slice(Math.max(0, position - 2), Math.min(semitones.length, position + 3));
    const localMedian = median(local);
    const current = semitones[position];
    const candidates = [current - 12, current, current + 12];
    const replacement = candidates.reduce((best, candidate) =>
      Math.abs(candidate - localMedian) < Math.abs(best - localMedian) ? candidate : best,
    );
    if (Math.abs(current - localMedian) > 7 && Math.abs(replacement - localMedian) < 4.5) {
      semitones[position] = replacement;
    }
  }
  validIndices.forEach((index, position) => {
    output[index] = 2 ** (semitones[position] / 12);
  });
  return output;
}

function longestInternalGap(voiced: boolean[]): number {
  const first = voiced.indexOf(true);
  const last = voiced.lastIndexOf(true);
  if (first < 0 || last <= first) return 0;
  let longest = 0;
  let current = 0;
  for (let index = first; index <= last; index += 1) {
    if (voiced[index]) current = 0;
    else {
      current += 1;
      longest = Math.max(longest, current);
    }
  }
  return longest;
}

function interpolatePitch(values: Array<number | null>): number[] {
  const valid = values.flatMap((value, index) =>
    value !== null && Number.isFinite(value) && value > 0 ? ([[index, value]] as Array<[number, number]>) : [],
  );
  if (valid.length < 5) {
    throw new DspSignalError(
      "insufficient_voicing",
      "I could not track enough pitch. Hold the vowel clearly and try again.",
      { voiced_frames: valid.length },
    );
  }
  return values.map((_, index) => {
    if (index <= valid[0][0]) return valid[0][1];
    if (index >= valid[valid.length - 1][0]) return valid[valid.length - 1][1];
    let rightIndex = 1;
    while (valid[rightIndex][0] < index) rightIndex += 1;
    const left = valid[rightIndex - 1];
    const right = valid[rightIndex];
    const mix = (index - left[0]) / Math.max(1, right[0] - left[0]);
    return left[1] * (1 - mix) + right[1] * mix;
  });
}

function savitzkyGolay(values: number[]): number[] {
  if (values.length < 5) return [...values];
  const coefficients =
    values.length >= 11
      ? [-36, 9, 44, 69, 84, 89, 84, 69, 44, 9, -36].map((value) => value / 429)
      : [-3, 12, 17, 12, -3].map((value) => value / 35);
  const radius = Math.floor(coefficients.length / 2);
  return values.map((_, index) =>
    coefficients.reduce(
      (sum, coefficient, offset) =>
        sum + coefficient * values[Math.min(values.length - 1, Math.max(0, index + offset - radius))],
      0,
    ),
  );
}

export function resampleContour(values: number[], size = DSP_CONTOUR_POINTS): number[] {
  if (!values.length) return Array.from({ length: size }, () => 0);
  if (values.length === 1) return Array.from({ length: size }, () => values[0]);
  return Array.from({ length: size }, (_, index) => {
    const position = (index * (values.length - 1)) / Math.max(1, size - 1);
    const left = Math.floor(position);
    const mix = position - left;
    return values[left] * (1 - mix) + values[Math.min(values.length - 1, left + 1)] * mix;
  });
}

function linearSlope(values: number[], start = 0, end = values.length): number {
  const length = end - start;
  if (length < 2) return 0;
  let xMean = 0;
  let yMean = 0;
  for (let index = 0; index < length; index += 1) {
    xMean += index / Math.max(1, length - 1);
    yMean += values[start + index];
  }
  xMean /= length;
  yMean /= length;
  let numerator = 0;
  let denominator = 0;
  for (let index = 0; index < length; index += 1) {
    const x = index / Math.max(1, length - 1);
    numerator += (x - xMean) * (values[start + index] - yMean);
    denominator += (x - xMean) ** 2;
  }
  return denominator ? numerator / denominator : 0;
}

export function extractContourFeatures(
  points: number[],
  evidence: Partial<Pick<ContourFeatures,
    | "duration_s"
    | "voiced_fraction"
    | "longest_voicing_gap_ms"
    | "central_rms_dip"
    | "terminal_energy_drop"
  >> = {},
): ContourFeatures {
  const contour = resampleContour(points);
  const edge = Math.max(3, Math.floor(contour.length / 10));
  const start = median(contour.slice(0, edge));
  const end = median(contour.slice(-edge));
  const midpoint = Math.floor(contour.length / 2);
  const minimum = Math.min(...contour);
  const minimumIndex = contour.indexOf(minimum);
  return {
    start,
    end,
    slope: linearSlope(contour),
    curvature: linearSlope(contour, midpoint) - linearSlope(contour, 0, midpoint),
    pitch_range: percentile(contour, 0.95) - percentile(contour, 0.05),
    minimum,
    dip_position: minimumIndex / Math.max(1, contour.length - 1),
    recovery: end - minimum,
    final_rise: linearSlope(contour, Math.floor(contour.length * 0.68)),
    duration_s: evidence.duration_s ?? 0.5,
    voiced_fraction: evidence.voiced_fraction ?? 1,
    longest_voicing_gap_ms: evidence.longest_voicing_gap_ms ?? 0,
    central_rms_dip: evidence.central_rms_dip ?? 0,
    terminal_energy_drop: evidence.terminal_energy_drop ?? 0,
  };
}

export function constrainedDtwDistance(left: number[], right: number[], window = 8): number {
  const a = resampleContour(left);
  const b = resampleContour(right);
  const size = DSP_CONTOUR_POINTS;
  const cost = Array.from({ length: size + 1 }, () => new Float64Array(size + 1).fill(Infinity));
  const steps = Array.from({ length: size + 1 }, () => new Uint16Array(size + 1));
  cost[0][0] = 0;
  for (let row = 1; row <= size; row += 1) {
    const firstColumn = Math.max(1, row - window);
    const lastColumn = Math.min(size, row + window);
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      const choices = [cost[row - 1][column], cost[row][column - 1], cost[row - 1][column - 1]];
      let choice = 0;
      if (choices[1] < choices[choice]) choice = 1;
      if (choices[2] < choices[choice]) choice = 2;
      const previous = choice === 0 ? [row - 1, column] : choice === 1 ? [row, column - 1] : [row - 1, column - 1];
      cost[row][column] = choices[choice] + Math.abs(a[row - 1] - b[column - 1]);
      steps[row][column] = steps[previous[0]][previous[1]] + 1;
    }
  }
  return cost[size][size] / Math.max(1, steps[size][size]) / 3;
}

function featureDistance(
  left: ContourFeatures,
  right: ContourFeatures,
  scales: number[],
): number {
  const distances = FEATURE_FIELDS.map((field, index) =>
    Math.min(4, Math.abs(left[field] - right[field]) / Math.max(1e-6, scales[index] ?? DEFAULT_FEATURE_SCALES[index])),
  );
  return distances.reduce((sum, value) => sum + value, 0) / distances.length;
}

function cueDistance(left: ContourFeatures, right: ContourFeatures): number {
  return (
    Math.abs(left.central_rms_dip - right.central_rms_dip) / 0.28 +
    Math.abs(left.longest_voicing_gap_ms - right.longest_voicing_gap_ms) / 70 +
    Math.abs(left.terminal_energy_drop - right.terminal_energy_drop) / 0.3
  ) / 3;
}

function trajectoryPlausibilityPenalty(tone: ToneId, features: ContourFeatures): number {
  // A falling huyền can finish low, but it should not recover into a strong
  // late rise. This cue keeps a pronounced hỏi recovery from being absorbed by
  // an otherwise nearby falling template when the practiced word is held out.
  if (tone !== "huyen" || features.recovery <= 2 || features.final_rise <= 1) return 0;
  return Math.min(
    0.35,
    0.04 * (features.recovery - 2) + 0.02 * (features.final_rise - 1),
  );
}

export function toneFamily(tone: ToneId, accent: Accent): ToneFamilyId {
  if (tone === "ngang") return "level";
  if (tone === "huyen" || tone === "nang") return "falling";
  if (tone === "sac") return "rising";
  if (tone === "nga") return accent === "south" ? "dipping" : "rising";
  return "dipping";
}

function softmax(scores: Map<string, number>, temperature: number): Map<string, number> {
  const entries = [...scores.entries()];
  const logits = entries.map(([, score]) => -score / Math.max(temperature, 1e-6));
  const maximum = Math.max(...logits);
  const exponentials = logits.map((value) => Math.exp(value - maximum));
  const total = exponentials.reduce((sum, value) => sum + value, 0);
  return new Map(entries.map(([key], index) => [key, exponentials[index] / Math.max(total, 1e-12)]));
}

const closePair = (left: ToneId, right: ToneId) => {
  const key = [left, right].sort().join(":");
  return key === "hoi:nga" || key === "nga:sac" || key === "huyen:nang";
};

export function classifyContour(
  contour: number[],
  features: ContourFeatures,
  signalConfidence: number,
  profile: ClassifierProfile,
): DspClassification {
  const templates = profile.templates.filter(
    (template) => template.accent === profile.accent && template.contour.length === DSP_CONTOUR_POINTS,
  );
  if (!templates.length) throw new Error(`No templates for ${profile.accent}`);
  const scales = profile.feature_scales.length === FEATURE_FIELDS.length
    ? profile.feature_scales
    : DEFAULT_FEATURE_SCALES;
  const templateScores = templates.map((template) => ({
    template,
    score:
      0.65 * constrainedDtwDistance(contour, template.contour) +
      0.35 * featureDistance(features, template.features, scales) +
      trajectoryPlausibilityPenalty(template.tone, features),
    cue: cueDistance(features, template.features),
  }));
  const toneScores = new Map<ToneId, number>();
  const cueScores = new Map<ToneId, number>();
  for (const tone of TONE_ORDER) {
    const entries = templateScores
      .filter((entry) => entry.template.tone === tone)
      .sort((left, right) => left.score - right.score);
    if (!entries.length) continue;
    // A learner produces one syllable, so the nearest validated exemplar is
    // the relevant template. Averaging a second, acoustically unrelated word
    // can move even a committed reference away from its own tone class.
    toneScores.set(tone, entries[0].score);
    cueScores.set(tone, entries[0].cue);
  }
  if (toneScores.size < TONE_ORDER.length) {
    throw new Error(`Classifier profile ${profile.version} is missing one or more tone templates.`);
  }
  let rankedTones = [...toneScores.keys()].sort(
    (left, right) => (toneScores.get(left) as number) - (toneScores.get(right) as number),
  );
  const baseMargin =
    (toneScores.get(rankedTones[1]) as number) - (toneScores.get(rankedTones[0]) as number);
  if (closePair(rankedTones[0], rankedTones[1]) && baseMargin <= 0.2) {
    rankedTones.slice(0, 2).forEach((tone) => {
      toneScores.set(tone, (toneScores.get(tone) as number) + 0.2 * (cueScores.get(tone) as number));
    });
  }
  rankedTones = [...toneScores.keys()].sort(
    (left, right) => (toneScores.get(left) as number) - (toneScores.get(right) as number),
  );
  const toneProbabilities = softmax(
    new Map([...toneScores].map(([tone, score]) => [tone, score])),
    profile.temperature,
  );

  let detectedTone = rankedTones[0];
  let detectedFamily = toneFamily(detectedTone, profile.accent);
  let classConfidence = toneProbabilities.get(detectedTone) as number;
  let margin =
    (toneScores.get(rankedTones[1]) as number) - (toneScores.get(rankedTones[0]) as number);
  let resultScores = new Map<string, number>(toneScores);
  if (profile.scoring_mode === "four_family") {
    const familyScores = new Map<ToneFamilyId, number>();
    for (const family of FAMILY_ORDER) {
      const members = [...toneScores]
        .filter(([tone]) => toneFamily(tone, profile.accent) === family)
        .map(([, score]) => score)
        .sort((left, right) => left - right);
      if (members.length) {
        const selected = members.slice(0, Math.min(2, members.length));
        familyScores.set(family, selected.reduce((sum, value) => sum + value, 0) / selected.length);
      }
    }
    const rankedFamilies = [...familyScores.keys()].sort(
      (left, right) => (familyScores.get(left) as number) - (familyScores.get(right) as number),
    );
    detectedFamily = rankedFamilies[0];
    detectedTone = rankedTones.find((tone) => toneFamily(tone, profile.accent) === detectedFamily) ?? detectedTone;
    const familyProbabilities = softmax(
      new Map([...familyScores].map(([family, score]) => [family, score])),
      profile.temperature,
    );
    classConfidence = familyProbabilities.get(detectedFamily) as number;
    margin =
      (familyScores.get(rankedFamilies[1]) as number) -
      (familyScores.get(rankedFamilies[0]) as number);
    resultScores = familyScores;
  }
  classConfidence = Math.min(0.95, classConfidence);
  const needsRetry =
    classConfidence < profile.abstention_threshold ||
    margin < profile.minimum_margin ||
    signalConfidence < 0.35;
  const alternatives = rankedTones.slice(0, 3).map((tone) => ({
    tone,
    family: toneFamily(tone, profile.accent),
    score: toneScores.get(tone) as number,
    probability: toneProbabilities.get(tone) as number,
  }));
  return {
    tone: detectedTone,
    family: detectedFamily,
    classConfidence,
    needsRetry,
    margin,
    alternatives,
    scores: Object.fromEntries(resultScores),
  };
}

function energyEvidence(levels: number[]): { centralRmsDip: number; terminalEnergyDrop: number } {
  const normalized = resampleContour(levels, DSP_CONTOUR_POINTS);
  const center = median(normalized.slice(Math.floor(0.42 * normalized.length), Math.floor(0.62 * normalized.length)));
  const flanks = median([
    ...normalized.slice(Math.floor(0.18 * normalized.length), Math.floor(0.38 * normalized.length)),
    ...normalized.slice(Math.floor(0.66 * normalized.length), Math.floor(0.86 * normalized.length)),
  ]);
  const terminal = median(normalized.slice(Math.floor(0.86 * normalized.length)));
  const preceding = median(
    normalized.slice(Math.floor(0.55 * normalized.length), Math.floor(0.78 * normalized.length)),
  );
  return {
    centralRmsDip: clamp(1 - center / Math.max(flanks, 1e-8)),
    terminalEnergyDrop: clamp(1 - terminal / Math.max(preceding, 1e-8)),
  };
}

export function analyzePcm(
  sourceSamples: Float32Array,
  sourceRate: number,
  profile: ClassifierProfile,
): DspAnalysis {
  const samples = resampleAudio(sourceSamples, sourceRate);
  const isolated = isolatePrimarySpeech(samples);
  const levels = frameRms(isolated.samples);
  const energyFloor = Math.max(0.006, Math.max(...levels) * 0.14);
  const pitches: Array<number | null> = [];
  const confidences: number[] = [];
  for (
    let start = 0, frameIndex = 0;
    start + DSP_FRAME_SIZE <= isolated.samples.length;
    start += DSP_HOP_SIZE, frameIndex += 1
  ) {
    if ((levels[frameIndex] ?? 0) < energyFloor) {
      pitches.push(null);
      continue;
    }
    const estimate = yinPitch(isolated.samples.slice(start, start + DSP_FRAME_SIZE));
    pitches.push(estimate?.f0 ?? null);
    if (estimate) confidences.push(estimate.confidence);
  }
  const corrected = removeOctaveSpikes(pitches);
  const voiced = corrected.map((value) => value !== null && Number.isFinite(value));
  const voicedFraction = voiced.filter(Boolean).length / Math.max(1, voiced.length);
  if (voiced.filter(Boolean).length < 5 || voicedFraction < 0.28) {
    throw new DspSignalError(
      "insufficient_voicing",
      "I could not track enough pitch. Hold the vowel clearly and try again.",
      { voiced_fraction: voicedFraction },
    );
  }
  const gapFrames = longestInternalGap(voiced);
  const longestVoicingGapMs = (gapFrames * DSP_HOP_SIZE * 1_000) / DSP_SAMPLE_RATE;
  if (longestVoicingGapMs > 180) {
    throw new DspSignalError(
      "voicing_gap",
      "Your voice broke for too long to grade this take. Try once more.",
      { longest_voicing_gap_ms: longestVoicingGapMs },
    );
  }
  const tracked = interpolatePitch(corrected);
  const validF0 = finiteValues(corrected);
  const medianF0 = median(validF0);
  const semitones = tracked.map((frequency) => 12 * Math.log2(frequency / medianF0));
  const contour = resampleContour(savitzkyGolay(semitones));
  const evidence = energyEvidence(levels);
  const features = extractContourFeatures(contour, {
    duration_s: isolated.quality.active_duration_s,
    voiced_fraction: voicedFraction,
    longest_voicing_gap_ms: longestVoicingGapMs,
    central_rms_dip: evidence.centralRmsDip,
    terminal_energy_drop: evidence.terminalEnergyDrop,
  });
  const durationScore = clamp(
    Math.min(isolated.quality.active_duration_s / 0.25, 1.5 / isolated.quality.active_duration_s),
  );
  const signalConfidence = clamp(
    0.34 * clamp((voicedFraction - 0.28) / 0.58) +
      0.34 * clamp((median(confidences) - 0.3) / 0.65) +
      0.16 * durationScore +
      0.1 * clamp((isolated.quality.rms - 0.0025) / 0.05) +
      0.06 * (1 - clamp(longestVoicingGapMs / 180)),
  );
  const quality: SignalQuality = {
    ...isolated.quality,
    voiced_fraction: voicedFraction,
    longest_voicing_gap_ms: longestVoicingGapMs,
  };
  return {
    contour,
    features,
    quality,
    signalConfidence,
    classification: classifyContour(contour, features, signalConfidence, profile),
  };
}
