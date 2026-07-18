import { demoAnalysis, FALLBACK_ECHO_SENTENCES, FALLBACK_PAYLOAD, pedagogicalContour } from "./fallbackData";

describe("committed offline experience", () => {
  it("starts with the Phương name minimal pair", () => {
    expect(FALLBACK_PAYLOAD.featured_queue.slice(0, 3)).toEqual(["phuong-name", "phuong-ward", "phuong-phoenix"]);
  });

  it("ships all six ma meanings and all eight Echo sentences", () => {
    expect(FALLBACK_PAYLOAD.words.filter((word) => word.id.startsWith("ma-")).map((word) => word.syllable)).toEqual(["ma", "mà", "má", "mả", "mã", "mạ"]);
    expect(FALLBACK_ECHO_SENTENCES).toHaveLength(8);
  });

  it("keeps every pedagogical contour at the 64-point API contract", () => {
    for (const tone of FALLBACK_PAYLOAD.tones) expect(pedagogicalContour(tone.id)).toHaveLength(64);
  });

  it("makes the signature demo a falling-tone meaning error", () => {
    const result = demoAnalysis("phuong-ward", "north");
    expect(result.correct).toBe(false);
    expect(result.tone_intended).toBe("ngang");
    expect(result.tone_detected).toBe("huyen");
    expect(result.detected_word_id).toBe("phuong-ward");
  });
});
