import { describe, expect, it } from "vitest";

import { FALLBACK_PAYLOAD } from "../fallbackData";
import type { ToneId } from "../types";
import {
  MA_SURFACES,
  PHUONG_SURFACES,
  TONE_MARK_LABEL,
  TONE_ORDER,
  toneSurfaceForWord,
} from "./toneLanguage";

describe("closed six-tone meaning maps", () => {
  const maWords = FALLBACK_PAYLOAD.words.filter((word) => word.id.startsWith("ma-"));
  const maByTone = new Map(maWords.map((word) => [word.tone, word]));

  it("covers all 30 directed ma meaning mismatches", () => {
    const directedMismatches = TONE_ORDER.flatMap((intended) =>
      TONE_ORDER.filter((detected) => detected !== intended).map((detected) => ({
        intended,
        detected,
      })),
    );

    expect(directedMismatches).toHaveLength(30);
    for (const { intended, detected } of directedMismatches) {
      const intendedWord = maByTone.get(intended);
      const detectedWord = maByTone.get(detected);
      expect(intendedWord, intended).toBeDefined();
      expect(detectedWord, detected).toBeDefined();
      expect(detectedWord?.syllable).toBe(MA_SURFACES[detected]);
      expect(detectedWord?.meaning_en.length).toBeGreaterThan(0);
      expect(toneSurfaceForWord(intendedWord!, detected)).toBe(MA_SURFACES[detected]);
      expect(TONE_MARK_LABEL[detected]).toMatch(/^dấu |không dấu$/);
    }
  });

  it("maps Phương to phường and phượng while keeping three forms meaning-null", () => {
    const group = FALLBACK_PAYLOAD.minimal_pair_groups?.find(
      (candidate) => candidate.id === "phuong-six-tones",
    );
    expect(group).toBeDefined();
    const byTone = new Map(group?.forms.map((form) => [form.tone, form]));

    expect(byTone.get("huyen")).toMatchObject({
      surface: "phường",
      word_id: "phuong-ward",
      meaning_en: "urban ward",
    });
    expect(byTone.get("nang")).toMatchObject({
      surface: "phượng",
      word_id: "phuong-phoenix",
      meaning_en: "phoenix",
    });
    for (const tone of ["sac", "hoi", "nga"] satisfies ToneId[]) {
      expect(byTone.get(tone)).toEqual({
        tone,
        surface: PHUONG_SURFACES[tone],
        word_id: null,
        meaning_en: null,
      });
    }
  });
});
