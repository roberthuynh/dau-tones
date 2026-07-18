import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { FALLBACK_WORDS } from "../../fallbackData";
import { ECHO_SCENES, fixtureAsResult, type EchoCourseResult } from "../../lib/echoCourse";
import { EchoResultPanel } from "./EchoResultPanel";

function renderResult(result: EchoCourseResult) {
  const onPracticeWord = vi.fn();
  const onContinue = vi.fn();
  render(
    <EchoResultPanel
      result={result}
      words={FALLBACK_WORDS}
      recordingUrl={null}
      revealArtUrl={null}
      onPlayLearner={vi.fn()}
      onPlayCorrect={vi.fn()}
      onPracticeWord={onPracticeWord}
      onContinue={onContinue}
      continuingLabel="Continue scene"
    />,
  );
  return { onPracticeWord, onContinue };
}

describe("EchoResultPanel", () => {
  it("makes a known tone-only meaning change explicit and routes back to Tone Shapes", () => {
    const { onPracticeWord } = renderResult(fixtureAsResult(ECHO_SCENES[0]));

    expect(screen.getByText("Here is exactly what changed.")).toBeTruthy();
    expect(screen.getByText(/dấu sắc · mother/)).toBeTruthy();
    expect(screen.getByText(/không dấu · ghost/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Practice this word in Tone Shapes/ }));
    expect(onPracticeWord).toHaveBeenCalledWith("ma-mother");
  });

  it("uses the correct state without inventing a difference", () => {
    const fixture = fixtureAsResult(ECHO_SCENES[0]);
    const targetTokens = fixture.target_text.split(/\s+/).map((token) => ({ target: token, heard: token, kind: "match" as const }));
    const correct: EchoCourseResult = { ...fixture, transcript: fixture.target_text, tokens: targetTokens, diff: targetTokens, explanation: "", literal_explanation: "" };
    const { onContinue } = renderResult(correct);

    expect(screen.getByText("Every tone mark landed.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue scene" }));
    expect(onContinue).toHaveBeenCalledOnce();
  });
});
