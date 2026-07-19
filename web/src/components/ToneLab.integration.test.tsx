import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { FALLBACK_PAYLOAD } from "../fallbackData";
import { ToneLab } from "./ToneLab";

const mocks = vi.hoisted(() => ({
  audioPlay: vi.fn(async () => undefined),
  audioStop: vi.fn(),
  recorderStart: vi.fn(async () => undefined),
  recorderStop: vi.fn(),
  generateDrill: vi.fn(async () => {
    throw new Error("offline");
  }),
  feedback: vi.fn(),
}));

vi.mock("../hooks/useAudioPlayback", () => ({
  useAudioPlayback: () => ({
    play: mocks.audioPlay,
    stop: mocks.audioStop,
    playing: false,
    progress: 0,
    error: null,
    clearError: vi.fn(),
  }),
}));

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    state: "idle",
    level: 0,
    elapsedMs: 0,
    error: null,
    toggle: vi.fn(),
    start: mocks.recorderStart,
    stop: mocks.recorderStop,
    clearError: vi.fn(),
  }),
}));

vi.mock("../lib/api", async (loadOriginal) => {
  const original = await loadOriginal<typeof import("../lib/api")>();
  return { ...original, generateDrill: mocks.generateDrill };
});

vi.mock("../lib/feedbackSound", () => ({ playFeedbackSound: mocks.feedback }));

describe("Tone Lab complete practice surface", () => {
  beforeAll(() => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  beforeEach(() => {
    localStorage.clear();
    Object.values(mocks).forEach((mock) => mock.mockClear());
    mocks.generateDrill.mockRejectedValue(new Error("offline"));
  });

  it("moves through listen, record, correct, wrong, coaching, and summary actions", async () => {
    const wordChange = vi.fn();
    const sessionUpdate = vi.fn();
    const useInDialogue = vi.fn();
    const requestMicrophone = vi.fn((_intent: "tone_shapes" | "dialogue", action: () => void) => action());
    render(
      <ToneLab
        payload={FALLBACK_PAYLOAD}
        accent="north"
        apiOnline={false}
        soundEnabled
        onWordChange={wordChange}
        onSessionUpdate={sessionUpdate}
        onUseInDialogue={useInDialogue}
        onRequestMicrophone={requestMicrophone}
      />,
    );

    expect(screen.getByRole("heading", { name: /^ma$/ })).toBeTruthy();
    expect(screen.getByText(/four acoustic families/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Listen \+ watch/ }));
    expect(mocks.audioPlay).toHaveBeenCalledWith("/audio/targets/north/ma-ghost.wav");

    fireEvent.click(screen.getByRole("button", { name: "Record your tone" }));
    expect(requestMicrophone).toHaveBeenCalledWith("tone_shapes", mocks.recorderStart);
    expect(mocks.recorderStart).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "✓ correct má" }));
    expect(screen.getByRole("heading", { name: /Correct family · má · dấu sắc/ })).toBeTruthy();
    expect(mocks.feedback).toHaveBeenCalledWith("correct", true);
    fireEvent.click(screen.getByRole("button", { name: /Use this tone in Dialogue Practice/ }));
    expect(useInDialogue).toHaveBeenCalledWith("ma-mother");

    fireEvent.click(screen.getByRole("button", { name: /Phương → phường/ }));
    expect(screen.getByRole("heading", { name: /Heard: phường · dấu huyền/ })).toBeTruthy();
    expect(screen.getAllByText("urban ward")).toHaveLength(2);
    expect(mocks.feedback).toHaveBeenCalledWith("wrong", true);

    fireEvent.click(screen.getByRole("button", { name: /Next shape/ }));
    expect(wordChange).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "New drill set" }));
    await waitFor(() => expect(mocks.generateDrill).toHaveBeenCalledWith("food", expect.any(Array)));
    await waitFor(() => expect(screen.getByText(/offline drill/)).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Finish" }));
    expect(screen.getByRole("dialog", { name: "Your tones, in focus." })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close summary" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(sessionUpdate).toHaveBeenCalled();
  });

  it("switches through all six ma controls and more-word definitions", () => {
    render(
      <ToneLab
        payload={FALLBACK_PAYLOAD}
        accent="south"
        apiOnline
        soundEnabled={false}
      />,
    );

    const toneRail = screen.getByRole("navigation", { name: "The six tones of ma" });
    for (const syllable of ["ma", "mà", "má", "mả", "mã", "mạ"]) {
      fireEvent.click(within(toneRail).getByRole("button", { name: new RegExp(`^${syllable}`) }));
    }
    fireEvent.click(screen.getByRole("button", { name: /Phương.*woman's name/ }));
    expect(screen.getByRole("heading", { name: /^Phương$/ })).toBeTruthy();
    expect(screen.getAllByText("Phương, a woman's name")).toHaveLength(2);
  });
});
