import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { FALLBACK_PAYLOAD } from "../fallbackData";
import { CoachPanel } from "./CoachPanel";

const currentWord = FALLBACK_PAYLOAD.words.find((word) => word.id === "ma-mother")!;
const localCoach = {
  observation: "Your ending stopped 2.1 semitones below the rising target.",
  coaching_sentence: "Lift your chin through the end of the vowel.",
  next_word: "ma-ghost",
  rationale: "Contrast the rise with a level shape while the motion is fresh.",
  source: "rules" as const,
};

it("keeps measured local coaching visible while GPT refinement runs", () => {
  render(
    <CoachPanel
      coach={localCoach}
      refinementStatus="refining"
      currentWord={currentWord}
      payload={FALLBACK_PAYLOAD}
      onNext={vi.fn()}
    />,
  );

  expect(screen.getByRole("status").textContent).toContain("GPT-5.6 is refining this cue");
  expect(screen.getByText(localCoach.observation)).toBeTruthy();
  expect(screen.getByText(localCoach.coaching_sentence)).toBeTruthy();
  expect(screen.getByText(/ready now/)).toBeTruthy();
});

it("makes an unavailable refinement non-blocking", () => {
  render(
    <CoachPanel
      coach={localCoach}
      refinementStatus="unavailable"
      currentWord={currentWord}
      payload={FALLBACK_PAYLOAD}
      onNext={vi.fn()}
    />,
  );

  expect(screen.getByRole("status").textContent).toContain("AI refinement unavailable");
  expect(screen.getByText(/keep practicing without waiting/)).toBeTruthy();
  expect(screen.getByRole("button", { name: /Next shape/i })).toBeTruthy();
});
