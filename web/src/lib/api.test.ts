import { afterEach, expect, it, vi } from "vitest";
import type { AnalysisResult } from "../types";
import { analyzeRecording, COACH_REFINEMENT_TIMEOUT_MS, getCoach, transcribeEcho } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("keeps a Dialogue recording actionable when transcription is unavailable", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 503 })));

  await expect(transcribeEcho(new Blob(["take"], { type: "audio/webm" }), "meet-family-learner-01", "north"))
    .rejects.toThrow("Dialogue transcription is unavailable right now. Your recording is still ready to replay beside the correct take.");
});

it("aligns the visible coach fallback with the bounded refinement timeout", async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn().mockImplementation((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
  })));

  const coaching = getCoach({} as AnalysisResult, [], "north");
  const expectation = expect(coaching).rejects.toThrow("GPT-5.6 coaching took too long. Your instant local coach is still ready.");
  await vi.advanceTimersByTimeAsync(COACH_REFINEMENT_TIMEOUT_MS);
  await expectation;
});

it("turns a 422 signal-quality response into an immediate retry result", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: "insufficient_voicing",
            message: "Hold the vowel for one comfortable beat.",
            needs_retry: true,
          },
        }),
        { status: 422, headers: { "Content-Type": "application/json" } },
      ),
    ),
  );

  const result = await analyzeRecording(
    new Blob([new Uint8Array(900)], { type: "audio/webm" }),
    "phuong-name",
    "ngang",
    "north",
  );

  expect(result.needs_retry).toBe(true);
  expect(result.signal_quality).toEqual({
    code: "insufficient_voicing",
    message: "Hold the vowel for one comfortable beat.",
  });
});
