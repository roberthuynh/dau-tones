import { afterEach, expect, it, vi } from "vitest";
import { analyzeRecording } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
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
