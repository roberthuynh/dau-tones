import { staticClassifierProfile } from "../data/classifierProfile";
import type {
  Accent,
  AnalysisResult,
  AnalysisWord,
  ClassifierProfile,
  ClassifierTemplate,
  ContourFeatures,
  MeaningVerdict,
  RetrySignalQuality,
  SemanticStatus,
  ToneId,
  Word,
  WordsPayload,
} from "../types";
import {
  analyzePcm,
  classifyContour,
  DspSignalError,
  extractContourFeatures,
  toneFamily,
  type DspAnalysis,
} from "./dspCore";
import type { LocalDspWorkerRequest, LocalDspWorkerResponse } from "./localDsp.worker";

const WORKER_TIMEOUT_MS = 3_500;
const TONE_MARK_LABELS: Record<ToneId, string> = {
  ngang: "không dấu",
  huyen: "dấu huyền",
  sac: "dấu sắc",
  hoi: "dấu hỏi",
  nga: "dấu ngã",
  nang: "dấu nặng",
};
const TONE_FORMS: Record<string, Record<ToneId, string>> = {
  ma: {
    ngang: "ma",
    huyen: "mà",
    sac: "má",
    hoi: "mả",
    nga: "mã",
    nang: "mạ",
  },
  phuong: {
    ngang: "Phương",
    huyen: "phường",
    sac: "phướng",
    hoi: "phưởng",
    nga: "phưỡng",
    nang: "phượng",
  },
};

type PendingWorkerRequest = {
  resolve: (analysis: DspAnalysis) => void;
  reject: (error: LocalDspError) => void;
  timeout: number;
};

let dspWorker: Worker | null = null;
let workerSequence = 0;
const pendingWorkerRequests = new Map<number, PendingWorkerRequest>();

export class LocalDspError extends Error {
  readonly code: string;
  readonly details: Record<string, string | number>;

  constructor(
    message: string,
    code = "analysis_failed",
    details: Record<string, string | number> = {},
  ) {
    super(message);
    this.name = "LocalDspError";
    this.code = code;
    this.details = details;
  }
}

function stripToneMarks(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function surfaceForTone(intended: Word, tone: ToneId): string {
  const mapped = TONE_FORMS[stripToneMarks(intended.surface ?? intended.syllable)]?.[tone];
  if (!mapped) return intended.surface ?? intended.syllable;
  const startsUppercase = /^[A-ZÀ-ỸĐ]/u.test(intended.surface ?? intended.syllable);
  return startsUppercase ? mapped[0].toLocaleUpperCase("vi") + mapped.slice(1) : mapped;
}

function detectedWord(intended: Word, tone: ToneId, words: Word[]): Word | undefined {
  const pairIds = intended.minimal_pair_ids ?? [];
  const pairs = pairIds.flatMap((id) => {
    const word = words.find((candidate) => candidate.id === id);
    return word ? [word] : [];
  });
  const base = stripToneMarks(intended.surface ?? intended.syllable);
  return (
    pairs.find((word) => word.tone === tone) ??
    words.find(
      (word) =>
        word.tone === tone && stripToneMarks(word.surface ?? word.syllable) === base,
    )
  );
}

function asAnalysisWord(word: Word): AnalysisWord {
  return {
    id: word.id,
    surface: word.surface ?? word.syllable,
    meaning_en: word.meaning_en,
    art_url: word.art_url,
  };
}

function fnvProfileHash(templates: ClassifierTemplate[]): string {
  let hash = 0x811c9dc5;
  const source = templates
    .map((template) => `${template.id}:${template.contour.map((value) => value.toFixed(4)).join(",")}`)
    .join("|");
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return `runtime-fnv1a32:${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function hasEveryTone(profile: ClassifierProfile): boolean {
  const tones = new Set(profile.templates.map((template) => template.tone));
  return (["ngang", "huyen", "sac", "hoi", "nga", "nang"] as ToneId[]).every((tone) =>
    tones.has(tone),
  );
}

export function resolveClassifierProfile(
  payload: WordsPayload,
  accent: Accent,
): ClassifierProfile {
  const supplied = payload.classifier_profiles?.[accent];
  if (supplied && supplied.accent === accent && hasEveryTone(supplied)) {
    const scoringMode =
      accent === "north" &&
      supplied.corpus_complete &&
      payload.scoring_modes.north?.includes("six")
        ? "six_tone"
        : "four_family";
    return { ...supplied, scoring_mode: scoringMode };
  }

  const committed = staticClassifierProfile(accent);
  const byWord = new Map(committed.templates.map((template) => [template.word_id, template]));
  for (const word of payload.words) {
    const reference = word.targets[accent];
    if (
      byWord.has(word.id) ||
      !reference?.validated ||
      reference.contour.length !== 64
    ) {
      continue;
    }
    byWord.set(word.id, {
      id: `${accent}/${word.id}`,
      word_id: word.id,
      tone: word.tone,
      accent,
      contour: reference.contour,
      features: extractContourFeatures(reference.contour),
      validated: true,
    });
  }
  const templates = [...byWord.values()];
  const missingTargetIds = payload.words
    .filter((word) => !byWord.has(word.id))
    .map((word) => `${accent}/${word.id}`);
  const corpusComplete =
    payload.words.length > 0 &&
    missingTargetIds.length === 0 &&
    byWord.size >= payload.words.length;
  const changed = templates.length !== committed.templates.length;
  return {
    ...committed,
    templates,
    manifest_hash: changed ? fnvProfileHash(templates) : committed.manifest_hash,
    corpus_complete: corpusComplete,
    missing_target_ids: missingTargetIds,
    scoring_mode:
      accent === "north" && corpusComplete && payload.scoring_modes.north?.includes("six")
        ? "six_tone"
        : "four_family",
  };
}

function failPendingWorkerRequests(error: LocalDspError): void {
  for (const pending of pendingWorkerRequests.values()) {
    window.clearTimeout(pending.timeout);
    pending.reject(error);
  }
  pendingWorkerRequests.clear();
}

function getWorker(): Worker | null {
  if (typeof Worker === "undefined") return null;
  if (dspWorker) return dspWorker;
  try {
    dspWorker = new Worker(new URL("./localDsp.worker.ts", import.meta.url), {
      type: "module",
      name: "dau-pitch-engine",
    });
    dspWorker.onmessage = (event: MessageEvent<LocalDspWorkerResponse>) => {
      const pending = pendingWorkerRequests.get(event.data.id);
      if (!pending) return;
      pendingWorkerRequests.delete(event.data.id);
      window.clearTimeout(pending.timeout);
      if (event.data.ok) pending.resolve(event.data.analysis);
      else {
        pending.reject(
          new LocalDspError(
            event.data.error.message,
            event.data.error.code,
            event.data.error.details,
          ),
        );
      }
    };
    dspWorker.onerror = () => {
      failPendingWorkerRequests(
        new LocalDspError(
          "The pitch engine stopped unexpectedly. Please try one more time.",
          "worker_failed",
        ),
      );
      dspWorker?.terminate();
      dspWorker = null;
    };
    return dspWorker;
  } catch {
    dspWorker = null;
    return null;
  }
}

function analyzeInWorker(
  samples: Float32Array,
  sampleRate: number,
  profile: ClassifierProfile,
): Promise<DspAnalysis> {
  const worker = getWorker();
  if (!worker) {
    try {
      return Promise.resolve(analyzePcm(samples, sampleRate, profile));
    } catch (error) {
      const resolved =
        error instanceof DspSignalError
          ? new LocalDspError(error.message, error.code, error.details)
          : new LocalDspError(
              error instanceof Error ? error.message : "The recording could not be analyzed.",
            );
      return Promise.reject(resolved);
    }
  }
  const id = ++workerSequence;
  const transferable = samples.buffer.slice(
    samples.byteOffset,
    samples.byteOffset + samples.byteLength,
  ) as ArrayBuffer;
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      pendingWorkerRequests.delete(id);
      reject(
        new LocalDspError(
          "The pitch reading took too long. Try one short, clear word.",
          "analysis_timeout",
        ),
      );
    }, WORKER_TIMEOUT_MS);
    pendingWorkerRequests.set(id, { resolve, reject, timeout });
    const request: LocalDspWorkerRequest = { id, samples: transferable, sampleRate, profile };
    worker.postMessage(request, [transferable]);
  });
}

async function decodeMono(blob: Blob): Promise<{ samples: Float32Array; sampleRate: number }> {
  const AudioContextConstructor = window.AudioContext;
  if (!AudioContextConstructor) {
    throw new LocalDspError(
      "This browser cannot decode the recording. Use a committed sample below.",
      "decode_unsupported",
    );
  }
  const context = new AudioContextConstructor();
  try {
    const decoded = await context.decodeAudioData((await blob.arrayBuffer()).slice(0));
    const mono = new Float32Array(decoded.length);
    for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
      const channelData = decoded.getChannelData(channel);
      for (let index = 0; index < channelData.length; index += 1) {
        mono[index] += channelData[index] / decoded.numberOfChannels;
      }
    }
    return { samples: mono, sampleRate: decoded.sampleRate };
  } catch (error) {
    if (error instanceof LocalDspError) throw error;
    throw new LocalDspError(
      "This browser could not decode that take. Try once more, or use a sample below.",
      "decode_failed",
    );
  } finally {
    void context.close();
  }
}

function meaningStatus(
  gradingMode: "six_tone" | "four_family",
  needsRetry: boolean,
  exactMatch: boolean,
  familyCorrect: boolean,
  knownDetectedWord: Word | undefined,
): SemanticStatus {
  if (needsRetry) return "uncertain";
  if (gradingMode === "six_tone" && exactMatch) return "exact_correct";
  if (gradingMode === "four_family" && familyCorrect && exactMatch) return "family_correct";
  if (gradingMode === "four_family" && familyCorrect) return "family_ambiguous";
  return knownDetectedWord ? "wrong_known_word" : "wrong_no_known_word";
}

function featureTips(
  learner: ContourFeatures,
  target: ContourFeatures,
  intendedTone: ToneId,
  correct: boolean,
): { codes: string[]; numeric: Record<string, number> } {
  const numeric = {
    start_semitones: learner.start - target.start,
    end_semitones: learner.end - target.end,
    slope: learner.slope - target.slope,
    pitch_range: learner.pitch_range - target.pitch_range,
    dip_position: learner.dip_position - target.dip_position,
    duration_s: learner.duration_s - target.duration_s,
    central_rms_dip: learner.central_rms_dip - target.central_rms_dip,
    terminal_energy_drop: learner.terminal_energy_drop - target.terminal_energy_drop,
  };
  if (correct) return { codes: [], numeric };
  const codes: string[] = [];
  if (numeric.start_semitones > 1.2) codes.push("started_too_high");
  else if (numeric.start_semitones < -1.2) codes.push("started_too_low");
  if ((intendedTone === "sac" || intendedTone === "nga") && learner.final_rise < target.final_rise - 1.2) {
    codes.push("no_final_rise");
  }
  if (intendedTone === "ngang" && learner.slope < -1.1) codes.push("fell_instead_of_level");
  if (target.pitch_range - learner.pitch_range > 1.15) codes.push("too_flat");
  if (intendedTone === "hoi" || intendedTone === "nga") {
    if (learner.recovery < target.recovery - 0.9) codes.push("missing_dip");
    else if (numeric.dip_position < -0.16) codes.push("dip_too_early");
    else if (numeric.dip_position > 0.16) codes.push("dip_too_late");
  }
  if (intendedTone === "nang") {
    if (numeric.duration_s > 0.18) codes.push("too_long");
    else if (numeric.duration_s < -0.18) codes.push("too_short");
  }
  if (
    intendedTone === "nga" &&
    learner.central_rms_dip < target.central_rms_dip - 0.16 &&
    learner.longest_voicing_gap_ms < target.longest_voicing_gap_ms - 35
  ) {
    codes.push("weak_glottal_break");
  }
  if (!codes.length) codes.push("too_flat");
  return { codes: [...new Set(codes)], numeric };
}

function retryAnalysis(
  intended: Word,
  accent: Accent,
  profile: ClassifierProfile,
  error: LocalDspError,
): AnalysisResult {
  const intendedFamily = toneFamily(intended.tone, accent);
  const intendedWord = asAnalysisWord(intended);
  const quality: RetrySignalQuality = {
    code: error.code,
    message: error.message,
    details: error.details,
  };
  const meaningVerdict: MeaningVerdict = {
    status: "uncertain",
    assertion_level: "none",
    detected_surface: null,
    detected_meaning_en: null,
    detected_word_id: null,
    tone_mark_label: TONE_MARK_LABELS[intended.tone],
  };
  return {
    tone_detected: intended.tone,
    tone_intended: intended.tone,
    detected_word_id: null,
    intended_word_id: intended.id,
    correct: false,
    confidence: 0,
    learner_contour: [],
    target_contour: intended.targets[accent]?.contour ?? [],
    detected_contour: null,
    tips_features: { codes: ["needs_retry"], numeric: {} },
    grading_mode: profile.scoring_mode,
    exact_verified: false,
    family_verified: false,
    alternatives: [],
    needs_retry: true,
    signal_quality: quality,
    tone_family: intendedFamily,
    intended_family: intendedFamily,
    exact_tone_match: false,
    family_correct: false,
    verification_level: "uncertain",
    tone_alternatives: [],
    word: intended.id,
    intended_word: intendedWord,
    detected_word: null,
    verdict_copy: null,
    target_validated: Boolean(intended.targets[accent]?.validated),
    semantic_status: "uncertain",
    class_confidence: 0,
    signal_confidence: 0,
    meaning_verdict: meaningVerdict,
    classifier_version: profile.version,
    classifier_manifest_hash: profile.manifest_hash,
  };
}

export function classifyLocalContour(
  contour: number[],
  duration: number,
  centralEnergyDip: number,
  accent: Accent,
): ToneId {
  const profile = staticClassifierProfile(accent);
  const features = extractContourFeatures(contour, {
    duration_s: duration,
    central_rms_dip: centralEnergyDip,
  });
  return classifyContour(contour, features, 1, profile).tone;
}

export async function analyzeLocally(
  blob: Blob,
  intended: Word,
  accent: Accent,
  payload: WordsPayload,
): Promise<AnalysisResult> {
  const profile = resolveClassifierProfile(payload, accent);
  const decoded = await decodeMono(blob);
  let analysis: DspAnalysis;
  try {
    analysis = await analyzeInWorker(decoded.samples, decoded.sampleRate, profile);
  } catch (error) {
    const resolved =
      error instanceof LocalDspError
        ? error
        : new LocalDspError(
            error instanceof Error ? error.message : "The recording could not be analyzed.",
          );
    return retryAnalysis(intended, accent, profile, resolved);
  }

  const classification = analysis.classification;
  const detectedTone = classification.tone;
  const intendedFamily = toneFamily(intended.tone, accent);
  const exactMatch = detectedTone === intended.tone;
  const familyCorrect = classification.family === intendedFamily;
  const knownDetectedWord = detectedWord(intended, detectedTone, payload.words);
  const semanticStatus = meaningStatus(
    profile.scoring_mode,
    classification.needsRetry,
    exactMatch,
    familyCorrect,
    knownDetectedWord,
  );
  const correct = semanticStatus === "exact_correct" || semanticStatus === "family_correct";
  const assertedWord =
    semanticStatus === "exact_correct" || semanticStatus === "family_correct"
      ? intended
      : semanticStatus === "wrong_known_word"
        ? knownDetectedWord
        : undefined;
  const targetContour = intended.targets[accent]?.contour ?? [];
  const targetTemplate = profile.templates.find((template) => template.word_id === intended.id);
  const targetFeatures = targetTemplate?.features ?? extractContourFeatures(targetContour);
  const tips = featureTips(analysis.features, targetFeatures, intended.tone, correct);
  const detectedSurface = classification.needsRetry
    ? null
    : (knownDetectedWord?.surface ?? knownDetectedWord?.syllable ?? surfaceForTone(intended, detectedTone));
  const meaningVerdict: MeaningVerdict = {
    status: semanticStatus,
    assertion_level:
      semanticStatus === "uncertain"
        ? "none"
        : profile.scoring_mode === "six_tone"
          ? "exact"
          : "family",
    detected_surface: detectedSurface,
    detected_meaning_en:
      semanticStatus === "wrong_known_word" || correct
        ? (assertedWord?.meaning_en ?? null)
        : null,
    detected_word_id:
      semanticStatus === "wrong_known_word" || correct ? (assertedWord?.id ?? null) : null,
    tone_mark_label: TONE_MARK_LABELS[detectedTone],
  };
  const detectedContour = knownDetectedWord?.targets[accent]?.contour ??
    profile.templates.find((template) => template.tone === detectedTone)?.contour ??
    null;
  const alternatives = classification.alternatives.map((alternative) => ({
    tone: alternative.tone,
    family: alternative.family,
    score: alternative.score,
    confidence: alternative.probability,
  }));
  let verdictCopy: string | null = null;
  if (semanticStatus === "wrong_known_word" && knownDetectedWord) {
    verdictCopy = `You meant ${intended.surface ?? intended.syllable}, ${intended.meaning_en}. You said ${knownDetectedWord.surface ?? knownDetectedWord.syllable}, ${knownDetectedWord.meaning_en}.`;
  } else if (semanticStatus === "wrong_no_known_word") {
    verdictCopy = `Dấu heard ${TONE_MARK_LABELS[detectedTone]} on “${intended.surface ?? intended.syllable}.” That form has no curated meaning in this lesson.`;
  }
  return {
    tone_detected: detectedTone,
    tone_intended: intended.tone,
    detected_word_id: meaningVerdict.detected_word_id,
    intended_word_id: intended.id,
    correct,
    confidence: classification.classConfidence,
    learner_contour: analysis.contour,
    target_contour: targetContour,
    detected_contour: correct ? null : detectedContour,
    tips_features: tips,
    grading_mode: profile.scoring_mode,
    exact_verified: profile.scoring_mode === "six_tone" && !classification.needsRetry,
    family_verified: !classification.needsRetry,
    alternatives,
    needs_retry: classification.needsRetry,
    signal_quality: analysis.quality,
    tone_family: classification.family,
    intended_family: intendedFamily,
    exact_tone_match: exactMatch,
    family_correct: familyCorrect,
    verification_level: classification.needsRetry
      ? "uncertain"
      : profile.scoring_mode === "six_tone"
        ? "exact"
        : "family",
    tone_alternatives: classification.alternatives,
    word: intended.id,
    intended_word: asAnalysisWord(intended),
    detected_word: assertedWord ? asAnalysisWord(assertedWord) : null,
    verdict_copy: verdictCopy,
    target_validated: Boolean(intended.targets[accent]?.validated),
    semantic_status: semanticStatus,
    class_confidence: classification.classConfidence,
    signal_confidence: analysis.signalConfidence,
    meaning_verdict: meaningVerdict,
    classifier_version: profile.version,
    classifier_manifest_hash: profile.manifest_hash,
  };
}
