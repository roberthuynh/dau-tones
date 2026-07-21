import { demoAnalysis, FALLBACK_PAYLOAD, mergeCommittedTargets, pedagogicalContour } from "./fallbackData";
import { ECHO_SCENES } from "./lib/echoCourse";

describe("committed offline experience", () => {
  it("starts with the complete six-tone ma lesson", () => {
    expect(FALLBACK_PAYLOAD.featured_queue.slice(0, 6)).toEqual(["ma-ghost", "ma-but", "ma-mother", "ma-grave", "ma-code", "ma-seedling"]);
  });

  it("ships all six ma meanings and the four-scene Echo course", () => {
    expect(FALLBACK_PAYLOAD.words.filter((word) => word.id.startsWith("ma-")).map((word) => word.syllable)).toEqual(["ma", "mà", "má", "mả", "mã", "mạ"]);
    expect(ECHO_SCENES).toHaveLength(4);
    expect(ECHO_SCENES.flatMap((scene) => scene.turns)).toHaveLength(26);
    expect(ECHO_SCENES.flatMap((scene) => scene.turns).filter((turn) => turn.role === "learner")).toHaveLength(13);
  });

  it("keeps every pedagogical contour at the 64-point API contract", () => {
    for (const tone of FALLBACK_PAYLOAD.tones) expect(pedagogicalContour(tone.id)).toHaveLength(64);
  });

  it("keeps validated bundled audio when the API reports a target pending", () => {
    const remote = structuredClone(FALLBACK_PAYLOAD);
    const ward = remote.words.find((word) => word.id === "phuong-ward")!;
    ward.targets.north = { audio_url: "", contour: [], validated: false };

    const merged = mergeCommittedTargets(remote);
    expect(merged.words.find((word) => word.id === "phuong-ward")!.targets.north).toEqual(
      FALLBACK_PAYLOAD.words.find((word) => word.id === "phuong-ward")!.targets.north,
    );
  });

  it("makes the signature demo a falling-tone meaning error", () => {
    const result = demoAnalysis("phuong-ward", "north");
    expect(result.correct).toBe(false);
    expect(result.tone_intended).toBe("ngang");
    expect(result.tone_detected).toBe("huyen");
    expect(result.detected_word_id).toBe("phuong-ward");
  });
});
