import type {
  Accent,
  AnalysisResult,
  SignalQuality,
  ToneFamilyId,
  ToneId,
  Word,
  WordsPayload,
} from "../types";

const DSP_SAMPLE_RATE = 11_025;
const FRAME_SIZE = 1_024;
const HOP_SIZE = 256;
const POINT_COUNT = 64;

const FAMILY_BY_TONE: Record<ToneId, ToneFamilyId> = {
  ngang: "level",
  huyen: "falling",
  sac: "rising",
  hoi: "dipping",
  nga: "rising",
  nang: "falling",
};

function familyForTone(tone: ToneId, accent: Accent): ToneFamilyId {
  if (accent === "south" && tone === "nga") return "dipping";
  return FAMILY_BY_TONE[tone];
}

export class LocalDspError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LocalDspError";
  }
}

function resample(samples: Float32Array, sourceRate: number): Float32Array {
  if (sourceRate === DSP_SAMPLE_RATE) return samples;
  const length = Math.max(1, Math.round((samples.length * DSP_SAMPLE_RATE) / sourceRate));
  const output = new Float32Array(length);
  const scale = (samples.length - 1) / Math.max(1, length - 1);
  for (let index = 0; index < length; index += 1) {
    const position = index * scale;
    const left = Math.floor(position);
    const mix = position - left;
    output[index] = samples[left] * (1 - mix) + samples[Math.min(samples.length - 1, left + 1)] * mix;
  }
  return output;
}

function frameRms(samples: Float32Array): number[] {
  const values: number[] = [];
  for (let start = 0; start + FRAME_SIZE <= samples.length; start += HOP_SIZE) {
    let sum = 0;
    for (let index = 0; index < FRAME_SIZE; index += 1) {
      const value = samples[start + index];
      sum += value * value;
    }
    values.push(Math.sqrt(sum / FRAME_SIZE));
  }
  return values;
}

function primarySpeech(samples: Float32Array): { segment: Float32Array; rms: number; peak: number } {
  const levels = frameRms(samples);
  const peakLevel = Math.max(0, ...levels);
  const threshold = Math.max(0.008, peakLevel * 0.15);
  const active = levels.map((value) => value >= threshold);
  const first = active.indexOf(true);
  const last = active.lastIndexOf(true);
  if (first < 0 || last < first) throw new LocalDspError("I could not hear a clear word. Try once more, a little closer to the microphone.");
  const start = Math.max(0, first * HOP_SIZE - Math.round(DSP_SAMPLE_RATE * 0.06));
  const end = Math.min(samples.length, last * HOP_SIZE + FRAME_SIZE + Math.round(DSP_SAMPLE_RATE * 0.06));
  const segment = samples.slice(start, end);
  if (segment.length / DSP_SAMPLE_RATE < 0.16) throw new LocalDspError("That was too short to grade. Hold the vowel for one comfortable beat.");
  let squareSum = 0;
  let peak = 0;
  for (const value of segment) {
    squareSum += value * value;
    peak = Math.max(peak, Math.abs(value));
  }
  return { segment, rms: Math.sqrt(squareSum / segment.length), peak };
}

function framePitch(frame: Float32Array): { f0: number; correlation: number } | null {
  let mean = 0;
  for (const value of frame) mean += value;
  mean /= frame.length;
  const minLag = Math.floor(DSP_SAMPLE_RATE / 500);
  const maxLag = Math.ceil(DSP_SAMPLE_RATE / 65);
  let bestLag = 0;
  let bestCorrelation = -1;
  for (let lag = minLag; lag <= maxLag; lag += 1) {
    let cross = 0;
    let energyA = 0;
    let energyB = 0;
    const limit = frame.length - lag;
    for (let index = 0; index < limit; index += 1) {
      const a = frame[index] - mean;
      const b = frame[index + lag] - mean;
      cross += a * b;
      energyA += a * a;
      energyB += b * b;
    }
    const correlation = cross / Math.sqrt(Math.max(1e-12, energyA * energyB));
    if (correlation > bestCorrelation) {
      bestCorrelation = correlation;
      bestLag = lag;
    }
  }
  if (bestLag === 0 || bestCorrelation < 0.5) return null;
  return { f0: DSP_SAMPLE_RATE / bestLag, correlation: bestCorrelation };
}

function percentile(values: number[], fraction: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round((sorted.length - 1) * fraction)))] ?? 0;
}

function interpolate(values: Array<number | null>): number[] {
  const valid = values.flatMap((value, index) => (value === null ? [] : [[index, value] as const]));
  if (valid.length < 5) throw new LocalDspError("I could not track enough pitch. Hold the vowel clearly and try again.");
  const output = new Array<number>(values.length);
  let cursor = 0;
  for (let index = 0; index < values.length; index += 1) {
    while (cursor + 1 < valid.length && valid[cursor + 1][0] < index) cursor += 1;
    const left = valid[cursor];
    const right = valid[Math.min(valid.length - 1, cursor + 1)];
    if (index <= valid[0][0]) output[index] = valid[0][1];
    else if (index >= valid[valid.length - 1][0]) output[index] = valid[valid.length - 1][1];
    else {
      const mix = (index - left[0]) / Math.max(1, right[0] - left[0]);
      output[index] = left[1] * (1 - mix) + right[1] * mix;
    }
  }
  return output;
}

function smooth(values: number[]): number[] {
  return values.map((_, index) => {
    const start = Math.max(0, index - 2);
    const end = Math.min(values.length, index + 3);
    return values.slice(start, end).reduce((sum, value) => sum + value, 0) / (end - start);
  });
}

function resampleContour(values: number[]): number[] {
  return Array.from({ length: POINT_COUNT }, (_, index) => {
    const position = (index * (values.length - 1)) / (POINT_COUNT - 1);
    const left = Math.floor(position);
    const mix = position - left;
    return values[left] * (1 - mix) + values[Math.min(values.length - 1, left + 1)] * mix;
  });
}

function features(contour: number[]) {
  const edge = 7;
  const start = contour.slice(0, edge).reduce((sum, value) => sum + value, 0) / edge;
  const end = contour.slice(-edge).reduce((sum, value) => sum + value, 0) / edge;
  const minimum = Math.min(...contour);
  const minimumIndex = contour.indexOf(minimum);
  return {
    start,
    end,
    slope: end - start,
    range: percentile(contour, 0.95) - percentile(contour, 0.05),
    dipPosition: minimumIndex / Math.max(1, contour.length - 1),
    recovery: end - minimum,
  };
}

export function classifyLocalContour(
  contour: number[],
  duration: number,
  centralEnergyDip: number,
  accent: Accent,
): ToneId {
  const shape = features(contour);
  const dipped = shape.dipPosition > 0.2 && shape.dipPosition < 0.78 && shape.recovery > 1.0;
  if (dipped && shape.range > 1.6) return accent === "north" && centralEnergyDip > 0.3 ? "nga" : "hoi";
  if (shape.slope > 1.25) return centralEnergyDip > 0.32 ? "nga" : "sac";
  if (shape.slope < -1.25) return duration < 0.32 ? "nang" : "huyen";
  return "ngang";
}

function detectedWord(intended: Word, tone: ToneId, words: Word[]): Word | undefined {
  const pairs = intended.minimal_pair_ids?.map((id) => words.find((word) => word.id === id)).filter(Boolean) as Word[] | undefined;
  return pairs?.find((word) => word.tone === tone) ?? words.find((word) => word.tone === tone && word.syllable.normalize("NFD").replace(/[\u0300-\u036f]/g, "") === intended.syllable.normalize("NFD").replace(/[\u0300-\u036f]/g, ""));
}

export async function analyzeLocally(blob: Blob, intended: Word, accent: Accent, payload: WordsPayload): Promise<AnalysisResult> {
  const AudioContextConstructor = window.AudioContext;
  if (!AudioContextConstructor) throw new LocalDspError("This browser cannot decode the recording. Use a committed sample below.");
  const context = new AudioContextConstructor();
  let decoded: AudioBuffer;
  try {
    decoded = await context.decodeAudioData((await blob.arrayBuffer()).slice(0));
  } catch {
    throw new LocalDspError("This browser could not decode that take. Try once more, or use a sample below.");
  } finally {
    void context.close();
  }
  const mono = new Float32Array(decoded.length);
  for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
    const data = decoded.getChannelData(channel);
    for (let index = 0; index < data.length; index += 1) mono[index] += data[index] / decoded.numberOfChannels;
  }
  const samples = resample(mono, decoded.sampleRate);
  const { segment, rms, peak } = primarySpeech(samples);
  const levels = frameRms(segment);
  const energyFloor = Math.max(0.007, Math.max(...levels) * 0.14);
  const pitches: Array<number | null> = [];
  const correlations: number[] = [];
  for (let start = 0, frameIndex = 0; start + FRAME_SIZE <= segment.length; start += HOP_SIZE, frameIndex += 1) {
    if ((levels[frameIndex] ?? 0) < energyFloor) {
      pitches.push(null);
      continue;
    }
    const estimate = framePitch(segment.slice(start, start + FRAME_SIZE));
    pitches.push(estimate?.f0 ?? null);
    if (estimate) correlations.push(estimate.correlation);
  }
  const tracked = interpolate(pitches);
  const medianF0 = percentile(tracked, 0.5);
  const semitones = tracked.map((frequency) => 12 * Math.log2(frequency / medianF0));
  const contour = resampleContour(smooth(semitones));
  const duration = segment.length / DSP_SAMPLE_RATE;
  const centerLevels = levels.slice(Math.floor(levels.length * 0.4), Math.ceil(levels.length * 0.62));
  const flankLevels = [...levels.slice(Math.floor(levels.length * 0.16), Math.floor(levels.length * 0.36)), ...levels.slice(Math.floor(levels.length * 0.68), Math.floor(levels.length * 0.88))];
  const center = percentile(centerLevels, 0.5);
  const flank = percentile(flankLevels, 0.5);
  const centralEnergyDip = Math.max(0, Math.min(1, 1 - center / Math.max(1e-6, flank)));
  const tone = classifyLocalContour(contour, duration, centralEnergyDip, accent);
  const intendedFamily = familyForTone(intended.tone, accent);
  const detectedFamily = familyForTone(tone, accent);
  const gradingMode = payload.scoring_modes[accent]?.includes("six") ? "six_tone" : "four_family";
  const exactMatch = tone === intended.tone;
  const familyCorrect = detectedFamily === intendedFamily;
  const correct = gradingMode === "six_tone" ? exactMatch : familyCorrect;
  const heard = correct ? intended : detectedWord(intended, tone, payload.words);
  const targetContour = intended.targets[accent]?.contour ?? [];
  const heardContour = heard?.targets[accent]?.contour ?? null;
  const targetShape = features(targetContour.length ? targetContour : contour);
  const learnerShape = features(contour);
  const codes: string[] = [];
  if (learnerShape.start > targetShape.start + 1.2) codes.push("started_too_high");
  if (learnerShape.end < targetShape.end - 1.2) codes.push("ended_too_low");
  if (targetShape.slope > 1 && learnerShape.slope < targetShape.slope - 1.2) codes.push("no_final_rise");
  if (!codes.length && !correct) codes.push("shape_drifted");
  const confidence = Math.min(0.9, Math.max(0.55, percentile(correlations, 0.5)));
  const quality: SignalQuality = {
    peak,
    rms,
    clipping_fraction: peak >= 0.995 ? 0.01 : 0,
    active_duration_s: duration,
    total_duration_s: samples.length / DSP_SAMPLE_RATE,
    voiced_fraction: pitches.filter((value) => value !== null).length / Math.max(1, pitches.length),
    longest_voicing_gap_ms: 0,
    island_count: 1,
  };
  const asWord = (word: Word) => ({ id: word.id, surface: word.surface ?? word.syllable, meaning_en: word.meaning_en, art_url: word.art_url });
  return {
    tone_detected: tone,
    tone_intended: intended.tone,
    intended_word_id: intended.id,
    detected_word_id: heard?.id ?? null,
    correct,
    confidence,
    learner_contour: contour,
    target_contour: targetContour,
    detected_contour: heard && heard.id !== intended.id ? heardContour : null,
    tips_features: { codes, numeric: { start: learnerShape.start - targetShape.start, end: learnerShape.end - targetShape.end, slope: learnerShape.slope - targetShape.slope } },
    grading_mode: gradingMode,
    exact_verified: gradingMode === "six_tone" && exactMatch,
    family_verified: true,
    alternatives: [{ tone, family: detectedFamily, score: 1 - confidence, confidence }],
    needs_retry: false,
    signal_quality: quality,
    tone_family: detectedFamily,
    intended_family: intendedFamily,
    exact_tone_match: exactMatch,
    family_correct: familyCorrect,
    verification_level: gradingMode === "six_tone" ? "exact" : "family",
    tone_alternatives: [{ tone, family: detectedFamily, score: 1 - confidence, probability: confidence }],
    word: intended.id,
    intended_word: asWord(intended),
    detected_word: heard ? asWord(heard) : null,
    verdict_copy: null,
    target_validated: Boolean(intended.targets[accent]?.validated),
  };
}
