import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import {
  ECHO_COURSE_SOURCE,
  ECHO_SCENES,
  committedMistakeArt,
  findLearnerTurnForFocus,
  focusForTurn,
  fixtureAsResult,
  isOwnedEchoObjectUrl,
  learnerTurns,
  readEchoCourseLocation,
  targetContourForFocus,
  toneOfVietnameseSurface,
  writeEchoCourseLocation,
} from "./echoCourse";
import { FALLBACK_PAYLOAD } from "../fallbackData";

describe("scene-based Echo curriculum", () => {
  it("bundles the canonical API course byte-for-byte", () => {
    const canonical = readFileSync(resolve(process.cwd(), "../api/data/echo_scenes.json"));
    const bundled = readFileSync(resolve(process.cwd(), "src/data/echo-scenes.generated.json"));
    expect(bundled).toEqual(canonical);
  });

  it("ships four linked scenes with 26 alternating turns and 13 substantial learner replies", () => {
    expect(ECHO_SCENES).toHaveLength(4);
    expect(ECHO_SCENES.flatMap((scene) => scene.turns)).toHaveLength(26);
    expect(ECHO_SCENES.flatMap(learnerTurns)).toHaveLength(13);

    for (const scene of ECHO_SCENES) {
      scene.turns.forEach((turn, index) => {
        expect(turn.role).toBe(index % 2 === 0 ? "minh" : "learner");
        expect(turn.audio_urls.north).toBe(`/audio/echo/north/${turn.id}.wav`);
        expect(turn.audio_urls.south).toBe(`/audio/echo/south/${turn.id}.wav`);
        expect(turn.focus.token.length).toBeGreaterThan(0);
        expect(turn.focus).toEqual(turn.focuses[0]);
      });
      for (const learner of learnerTurns(scene)) {
        expect(learner.text.trim().split(/\s+/).length).toBeGreaterThanOrEqual(7);
      }
    }
  });

  it("derives every turn and focus from the canonical API curriculum", () => {
    for (const sourceScene of ECHO_COURSE_SOURCE.scenes) {
      const browserScene = ECHO_SCENES.find((scene) => scene.id === sourceScene.id);
      expect(browserScene).toBeDefined();
      for (const sourceTurn of sourceScene.turns) {
        const browserTurn = browserScene?.turns.find((turn) => turn.id === sourceTurn.id);
        expect(browserTurn).toMatchObject({
          role: sourceTurn.speaker,
          text: sourceTurn.text,
          gloss_en: sourceTurn.gloss_en,
        });
        expect(browserTurn?.focuses).toEqual(sourceTurn.focuses.map((focus) => ({
          token_index: focus.token_index,
          token: focus.token,
          tone: focus.tone,
          ...(focus.word_id ? { word_id: focus.word_id } : {}),
          ...(focus.meaning_en ? { meaning_en: focus.meaning_en } : {}),
        })));
      }
    }
  });

  it("keeps one complete offline meaning fixture per scene", () => {
    expect(ECHO_SCENES.map((scene) => ({
      id: scene.fixture.id,
      turn_id: scene.fixture.turn_id,
      transcript: scene.fixture.heard_text,
      audio_url: scene.fixture.audio_url,
    }))).toEqual([
      {
        id: "meet-family-said-ghost",
        turn_id: "meet-family-learner-01",
        transcript: "Được chứ, tối nay tôi về nhà ăn cơm với ma và cả gia đình.",
        audio_url: "/audio/demos/echo/meet-family-said-ghost.wav",
      },
      {
        id: "family-dinner-seedling-code",
        turn_id: "family-dinner-learner-03",
        transcript: "Cửa nhà màu xanh, mạ cửa là hai ba sáu, bạn cứ vào nhé.",
        audio_url: "/audio/demos/echo/family-dinner-seedling-code.wav",
      },
      {
        id: "pho-shop-said-listless",
        turn_id: "pho-shop-learner-01",
        transcript: "Cho tôi một tô phờ bò, một đĩa rau và một ly nước.",
        audio_url: "/audio/demos/echo/pho-shop-said-listless.wav",
      },
      {
        id: "around-ward-grave-became-ghost",
        turn_id: "around-ward-learner-03",
        transcript: "Tôi không sợ ma, nhưng tôi không đi gần ma vào ban đêm.",
        audio_url: "/audio/demos/echo/around-ward-grave-became-ghost.wav",
      },
    ]);
    for (const scene of ECHO_SCENES) {
      const result = fixtureAsResult(scene);
      expect(result.scene_id).toBe(scene.id);
      expect(result.turn_id).toBe(scene.fixture.turn_id);
      expect(result.source).toBe("fixture");
      expect(result.tokens.some((token) => token.kind !== "match")).toBe(true);
      expect(result.practice_word_ids?.length).toBeGreaterThan(0);
    }
  });

  it("treats only generated blob URLs as browser-owned", () => {
    expect(isOwnedEchoObjectUrl("blob:http://localhost/learner-take")).toBe(true);
    expect(isOwnedEchoObjectUrl("/audio/demos/echo/meet-family-said-ghost.wav")).toBe(false);
    expect(isOwnedEchoObjectUrl(null)).toBe(false);
  });

  it("routes known literal mistakes to committed reveal art", () => {
    expect(committedMistakeArt(fixtureAsResult(ECHO_SCENES[0]))).toBe("/art/scenes/mistake-ghost-dinner.webp");
    expect(committedMistakeArt(fixtureAsResult(ECHO_SCENES[1]))).toBe("/art/scenes/mistake-seedling-code.webp");
  });

  it("restores scene, learner turn, and focus from URL query state", () => {
    const location = readEchoCourseLocation("?mode=echo&scene=family-dinner&turn=family-dinner-learner-03&focus=ma-code");
    expect(location).toEqual({ sceneId: "family-dinner", turnId: "family-dinner-learner-03", focus: "ma-code" });
  });

  it("round-trips a Tone Shapes word into the matching dialogue reply", () => {
    expect(findLearnerTurnForFocus(ECHO_SCENES, "ma-code")).toMatchObject({
      scene: { id: "family-dinner" },
      turn: { id: "family-dinner-learner-03" },
    });
    expect(findLearnerTurnForFocus(ECHO_SCENES, "mả")).toMatchObject({
      scene: { id: "around-ward" },
      turn: { id: "around-ward-learner-03" },
    });
    const graveTurn = findLearnerTurnForFocus(ECHO_SCENES, "ma-grave")?.turn;
    expect(graveTurn && focusForTurn(graveTurn, "ma-grave")).toMatchObject({
      token: "mả",
      tone: "hoi",
      word_id: "ma-grave",
    });
  });

  it("drives Cô Dấu from the focus word's committed accent contour", () => {
    const source = FALLBACK_PAYLOAD.words[0];
    const committedNorthContour = [3.25, 2.5, 1.75, 1];
    const focusWord = {
      ...source,
      id: "focus-word",
      targets: {
        ...source.targets,
        north: { ...source.targets.north, contour: committedNorthContour },
      },
    };
    expect(targetContourForFocus(
      { token_index: 0, token: "má", tone: "sac", word_id: focusWord.id },
      "north",
      [focusWord],
    )).toEqual(committedNorthContour);
    expect(targetContourForFocus(
      { token_index: 0, token: "má", tone: "sac" },
      "north",
      [focusWord],
    )).toBeNull();
  });

  it("rejects partner turn IDs as active learner state", () => {
    const location = readEchoCourseLocation("?scene=pho-shop&turn=pho-shop-minh-02");
    expect(location.sceneId).toBe("pho-shop");
    expect(location.turnId).toBe("pho-shop-learner-01");
  });

  it("writes stable shareable course query state", () => {
    window.history.replaceState({}, "", "/?sound=on");
    expect(writeEchoCourseLocation("around-ward", "around-ward-learner-03", "ma-grave"))
      .toBe("?sound=on&mode=dialogue&scene=around-ward&turn=around-ward-learner-03&focus=ma-grave");
  });

  it("names every Vietnamese tone mark without a lexical lookup", () => {
    expect(["ma", "mà", "má", "mả", "mã", "mạ"].map(toneOfVietnameseSurface))
      .toEqual(["ngang", "huyen", "sac", "hoi", "nga", "nang"]);
  });
});
