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
  try {
    const response = await fetch(`${API_PREFIX}${path}`, { ...init, signal: controller.signal });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
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
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The analysis took too long. Please try one short, clear word.");
    }
    if (error instanceof ApiError) throw error;
    throw new ApiError("Dấu could not reach the local API. Start it with ./dev.sh, or use a sample below.");
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
    return await json<AnalysisResult>("/analyze", { method: "POST", body: form }, 20_000);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422 && error.detail?.needs_retry) {
      return {
        tone_detected: intendedTone as AnalysisResult["tone_detected"],
        tone_intended: intendedTone as AnalysisResult["tone_intended"],
        intended_word_id: wordId,
        correct: false,
        confidence: 0,
        learner_contour: [],
        target_contour: [],
        tips_features: {},
        needs_retry: true,
        signal_quality: { label: error.detail.code ?? "needs_retry", message: error.detail.message ?? error.message },
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
    14_000,
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

export async function getReveal(revealId: string): Promise<{ status: string; image_url?: string }> {
  return json(`/echo/reveals/${encodeURIComponent(revealId)}`, undefined, 8_000);
}
