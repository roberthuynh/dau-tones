import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EchoMode } from "../EchoMode";
import { FALLBACK_PAYLOAD } from "../../fallbackData";
import { useRecorder } from "../../hooks/useRecorder";

vi.mock("../../hooks/useRecorder", () => ({ useRecorder: vi.fn() }));

describe("EchoMode committed fixture replay", () => {
  const play = vi.fn().mockResolvedValue(undefined);
  const pause = vi.fn();
  const audio = vi.fn(function AudioMock(this: Record<string, unknown>, source: string) {
    this.src = source;
    this.play = play;
    this.pause = pause;
    this.currentTime = 0;
    this.paused = true;
    this.duration = 1;
    this.addEventListener = vi.fn();
  });
  const revokeObjectUrl = vi.fn();
  const createObjectUrl = vi.fn(() => "blob:http://localhost/learner-take");
  let deliverRecording: (blob: Blob) => void | Promise<void>;

  beforeEach(() => {
    window.history.replaceState({}, "", "/?mode=dialogue");
    play.mockClear();
    pause.mockClear();
    audio.mockClear();
    revokeObjectUrl.mockClear();
    createObjectUrl.mockClear();
    vi.mocked(useRecorder).mockImplementation((options) => {
      deliverRecording = options.onRecording;
      return {
        state: "idle",
        level: 0,
        elapsedMs: 0,
        error: null,
        toggle: vi.fn(),
        start: vi.fn().mockResolvedValue(undefined),
        stop: vi.fn(),
        clearError: vi.fn(),
      };
    });
    vi.stubGlobal("Audio", audio);
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    Object.defineProperty(URL, "createObjectURL", { value: createObjectUrl, configurable: true });
    Object.defineProperty(URL, "revokeObjectURL", { value: revokeObjectUrl, configurable: true });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("loads the committed recording as Your take and never revokes its static URL", () => {
    const { unmount } = render(
      <EchoMode accent="north" payload={FALLBACK_PAYLOAD} liveTranscription={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /No key or no Vietnamese/i }));
    const replay = screen.getByRole("button", { name: /Your take/i }) as HTMLButtonElement;
    expect(replay.disabled).toBe(false);
    const activeBubble = screen.getByRole("list", { name: /Meet the family dialogue/i }).querySelector('[aria-current="step"]');
    expect(activeBubble?.classList.contains("is-complete")).toBe(true);
    fireEvent.click(replay);
    expect(audio).toHaveBeenCalledWith("/audio/demos/echo/meet-family-said-ghost.wav");
    expect(play).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: /Correct take/i }));
    expect(pause).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Practice again" }));
    expect(screen.getByRole("button", { name: "Record your reply" })).toBeTruthy();
    expect(screen.queryByText("Here is exactly what changed.")).toBeNull();
    expect(activeBubble?.classList.contains("is-complete")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: /Family dinner/i }));
    unmount();
    expect(revokeObjectUrl).not.toHaveBeenCalled();
  });

  it("keeps a no-key learner recording replayable beside the correct take", async () => {
    render(<EchoMode accent="north" payload={FALLBACK_PAYLOAD} liveTranscription={false} />);

    fireEvent.click(screen.getByRole("button", { name: /No key or no Vietnamese/i }));
    await act(async () => {
      await deliverRecording(new Blob(["learner audio"], { type: "audio/webm" }));
    });

    expect(screen.getByText("Your recording is ready.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Your take/i }));
    expect(audio).toHaveBeenCalledWith("blob:http://localhost/learner-take");
    expect(play).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /Continue scene without a score/i })).toBeTruthy();
  });
});
