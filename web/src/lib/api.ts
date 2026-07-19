import type {
  Accent,
  AnalysisResult,
  CoachResult,
  EchoResult,
  EchoSentence,
  HealthPayload,
  WordsPayload,
} from "../types";

const API_PREFIX = "/api";
const ANALYSIS_TIMEOUT_MS = 6_000;
// The server allows GPT-5.6 up to 18 seconds; keep two seconds for transport
// so the browser receives its deterministic fallback instead of aborting first.
export const COACH_REFINEMENT_TIMEOUT_MS = 22_000;
let analysisWarmup: Promise<void> | null = null;

type EndpointErrorCopy = {
  timeout: string;
  unavailable: string;
};

function endpointErrorCopy(path: string): EndpointErrorCopy {
  if (path === "/coach") {
    return {
      timeout: "GPT-5.6 coaching took too long. Your instant local coach is still ready.",
      unavailable: "GPT-5.6 coaching is unavailable right now. Your instant local coach is still ready.",
    };
  }
  if (path === "/drills/generate") {
    return {
      timeout: "The new drill took too long. Dấu will use the committed practice sequence.",
      unavailable: "The new drill service is unavailable. Dấu will use the committed practice sequence.",
    };
  }
  if (path === "/echo/transcribe") {
    return {
      timeout: "Dialogue transcription took too long. Your recording is still ready to replay beside the correct take.",
      unavailable: "Dialogue transcription is unavailable right now. Your recording is still ready to replay beside the correct take.",
    };
  }
  if (path === "/echo/speak") {
    return {
      timeout: "Correct Dialogue playback took too long. Try the committed take again.",
      unavailable: "Correct Dialogue playback is unavailable. Read the line, then continue with your reply.",
    };
  }
  if (path.startsWith("/echo/reveals/")) {
    return {
      timeout: "The optional mistake illustration took too long. Your transcript feedback is still complete.",
      unavailable: "The optional mistake illustration is unavailable. Your transcript feedback is still complete.",
    };
  }
  if (path === "/analyze") {
    return {
      timeout: "The compatibility analysis took too long. Try one short, clear word.",
      unavailable: "The compatibility analyzer is unavailable. Browser pitch grading and the scored samples still work.",
    };
  }
  if (path.startsWith("/demos/")) {
    return {
      timeout: "That scored sample took too long to load. Try another sample.",
      unavailable: "That scored sample is unavailable. Live browser grading still works.",
    };
  }
  if (path === "/words") {
    return {
      timeout: "The lesson library took too long to refresh. The committed lessons are still available.",
      unavailable: "The lesson library could not refresh. The committed lessons are still available.",
    };
  }
  if (path === "/healthz") {
    return {
      timeout: "The coaching API health check took too long. Local pitch grading still works.",
      unavailable: "The coaching API is offline. Local pitch grading and committed lessons still work.",
    };
  }
  return {
    timeout: "That request took too long. Please try again.",
    unavailable: "Dấu could not reach that service. Please try again.",
  };
}

export class ApiError extends Error {
  status?: number;
  detail?: { code?: string; message?: string; needs_retry?: boolean };

  constructor(message: string, status?: number, detail?: { code?: string; message?: string; needs_retry?: boolean }) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request(path: string, init?: RequestInit, timeoutMs = 12_000): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const errorCopy = endpointErrorCopy(path);
  try {
    const response = await fetch(`${API_PREFIX}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      let detail = errorCopy.unavailable;
      let structuredDetail: { code?: string; message?: string; needs_retry?: boolean } | undefined;
      try {
        const payload = (await response.json()) as { detail?: string | { message?: string } };
        if (typeof payload.detail === "string") detail = payload.detail;
        if (typeof payload.detail === "object" && payload.detail) {
          structuredDetail = payload.detail;
          if (payload.detail.message) detail = payload.detail.message;
        }
      } catch {
        // The HTTP status is enough when an upstream returns a non-JSON body.
      }
      throw new ApiError(detail, response.status, structuredDetail);
    }
    return response;
  } catch (error) {
    if (typeof error === "object" && error !== null && "name" in error && error.name === "AbortError") {
      throw new ApiError(errorCopy.timeout);
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError(errorCopy.unavailable);
  } finally {
    window.clearTimeout(timeout);
  }
}

async function json<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const response = await request(path, init, timeoutMs);
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthPayload> {
  return json<HealthPayload>("/healthz", undefined, 12_000);
}

export function warmAnalysis(): Promise<void> {
  analysisWarmup ??= request("/analysis/warmup", { method: "POST" }, 60_000).then(() => undefined);
  return analysisWarmup;
}

export function getWords(): Promise<WordsPayload> {
  return json<WordsPayload>("/words", undefined, 8_000);
}

export async function analyzeRecording(audio: Blob, wordId: string, intendedTone: string, accent: Accent): Promise<AnalysisResult> {
  const form = new FormData();
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "m4a" : audio.type.includes("wav") ? "wav" : "webm";
  form.append("audio", audio, `learner.${extension}`);
  form.append("word", wordId);
  form.append("word_id", wordId);
  form.append("intended_tone", intendedTone);
  form.append("accent", accent);
  try {
    return await json<AnalysisResult>("/analyze", { method: "POST", body: form }, ANALYSIS_TIMEOUT_MS);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422 && error.detail?.needs_retry) {
      const tone = intendedTone as AnalysisResult["tone_intended"];
      const familyByTone: Record<AnalysisResult["tone_intended"], AnalysisResult["tone_family"]> = {
        ngang: "level",
        huyen: "falling",
        sac: "rising",
        hoi: "dipping",
        nga: accent === "south" ? "dipping" : "rising",
        nang: "falling",
      };
      const family = familyByTone[tone];
      return {
        tone_detected: tone,
        tone_intended: tone,
        intended_word_id: wordId,
        detected_word_id: null,
        correct: false,
        confidence: 0,
        learner_contour: [],
        target_contour: [],
        detected_contour: null,
        tips_features: { codes: [], numeric: {} },
        grading_mode: "four_family",
        exact_verified: false,
        family_verified: false,
        alternatives: [],
        needs_retry: true,
        signal_quality: { code: error.detail.code ?? "needs_retry", message: error.detail.message ?? error.message },
        tone_family: family,
        intended_family: family,
        exact_tone_match: false,
        family_correct: false,
        verification_level: "uncertain",
        tone_alternatives: [],
        word: wordId,
        intended_word: { id: wordId, surface: wordId, meaning_en: "", art_url: "" },
        detected_word: null,
        verdict_copy: null,
        target_validated: false,
        semantic_status: "uncertain",
        class_confidence: 0,
        signal_confidence: 0,
        meaning_verdict: {
          status: "uncertain",
          assertion_level: "none",
          detected_surface: null,
          detected_meaning_en: null,
          detected_word_id: null,
          tone_mark_label: "",
        },
        classifier_version: "retry-v1",
        classifier_manifest_hash: "",
      };
    }
    throw error;
  }
}

export async function analyzeCommittedDemo(demoId: string, wordId: string, intendedTone: string, accent: Accent): Promise<AnalysisResult> {
  const response = await request(`/demos/${encodeURIComponent(demoId)}.wav`, undefined, 10_000);
  const audio = await response.blob();
  return analyzeRecording(audio, wordId, intendedTone, accent);
}

export function getCoach(verdict: AnalysisResult, history: AnalysisResult[], accent: Accent): Promise<CoachResult> {
  return json<CoachResult>(
    "/coach",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ verdict, history: history.slice(-12), accent }),
    },
    COACH_REFINEMENT_TIMEOUT_MS,
  );
}

export function generateDrill(theme: "food" | "family" | "travel", history: AnalysisResult[]): Promise<{ word_ids: string[]; rationale: string }> {
  return json(
    "/drills/generate",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme, size: 7, history: history.slice(-12) }),
    },
    14_000,
  );
}

export async function getEchoSentences(): Promise<EchoSentence[]> {
  const payload = await json<EchoSentence[] | { sentences: EchoSentence[] }>("/echo/sentences", undefined, 8_000);
  return Array.isArray(payload) ? payload : payload.sentences;
}

export async function transcribeEcho(audio: Blob, sentenceId: string, accent: Accent): Promise<EchoResult> {
  const form = new FormData();
  const extension = audio.type.includes("ogg") ? "ogg" : audio.type.includes("mp4") ? "m4a" : "webm";
  form.append("audio", audio, `echo.${extension}`);
  form.append("sentence_id", sentenceId);
  form.append("accent", accent);
  return json<EchoResult>("/echo/transcribe", { method: "POST", body: form }, 35_000);
}

export function transcribeEchoDemo(sentenceId: string, demoId: string): Promise<EchoResult> {
  const form = new FormData();
  form.append("sentence_id", sentenceId);
  form.append("demo_id", demoId);
  return json<EchoResult>("/echo/transcribe", { method: "POST", body: form }, 20_000);
}

export async function getEchoSpeech(sentenceId: string, accent: Accent): Promise<string> {
  const response = await request(
    "/echo/speak",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sentence_id: sentenceId, accent }),
    },
    30_000,
  );
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    const payload = (await response.json()) as { audio_url?: string; url?: string };
    const url = payload.audio_url ?? payload.url;
    if (!url) throw new ApiError("The correct playback was not available.");
    return url;
  }
  return URL.createObjectURL(await response.blob());
}

const ECHO_REVEAL_CACHE = "dau-echo-reveals-v1";

function revealCacheKey(revealId: string): Request {
  return new Request(`${window.location.origin}/__dau-cache/echo-reveal/${encodeURIComponent(revealId)}`);
}

async function cachedReveal(revealId: string): Promise<Blob | null> {
  if (!("caches" in window)) return null;
  try {
    const cache = await window.caches.open(ECHO_REVEAL_CACHE);
    const response = await cache.match(revealCacheKey(revealId));
    return response ? await response.blob() : null;
  } catch {
    return null;
  }
}

async function rememberReveal(revealId: string, image: Blob): Promise<void> {
  if (!("caches" in window)) return;
  try {
    const cache = await window.caches.open(ECHO_REVEAL_CACHE);
    await cache.put(
      revealCacheKey(revealId),
      new Response(image, { headers: { "Content-Type": image.type || "image/png" } }),
    );
  } catch {
    // Cache Storage can be unavailable or full; the current reveal still renders.
  }
}

export async function getOrCreateReveal(revealId: string): Promise<string> {
  const existing = await cachedReveal(revealId);
  if (existing) return URL.createObjectURL(existing);

  const response = await request(
    `/echo/reveals/${encodeURIComponent(revealId)}`,
    { method: "POST" },
    130_000,
  );
  const image = await response.blob();
  if (!image.type.startsWith("image/")) {
    throw new ApiError("The literal meaning picture could not be generated.");
  }
  await rememberReveal(revealId, image);
  return URL.createObjectURL(image);
}
