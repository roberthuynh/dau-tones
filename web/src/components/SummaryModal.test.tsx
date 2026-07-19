import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { FALLBACK_PAYLOAD } from "../fallbackData";
import { SummaryModal } from "./SummaryModal";

const canvasContext = {
  beginPath: vi.fn(),
  roundRect: vi.fn(),
  fill: vi.fn(),
  fillRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn((text: string) => ({ width: text.length * 12 })),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  fillStyle: "",
  font: "",
};

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(canvasContext as unknown as CanvasRenderingContext2D);
  vi.spyOn(HTMLCanvasElement.prototype, "toBlob").mockImplementation((callback) => callback(new Blob(["summary"], { type: "image/png" })));
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:http://localhost/summary"),
    revokeObjectURL: vi.fn(),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("renders session evidence and exports the share card without Web Share", async () => {
  const onClose = vi.fn();
  render(
    <SummaryModal
      open
      onClose={onClose}
      stats={{ sac: { attempts: 3, correct: 2 }, ngang: { attempts: 1, correct: 1 } }}
      streak={2}
      coachLine="Lift your chin through the final rise and keep the vowel open."
      tones={FALLBACK_PAYLOAD.tones}
    />,
  );

  expect(screen.getByText("75%")).toBeTruthy();
  expect(screen.getByText("3 of 4 landed")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /Share summary card/ }));

  await waitFor(() => expect(HTMLCanvasElement.prototype.toBlob).toHaveBeenCalled());
  expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce();
  expect(canvasContext.fillText).toHaveBeenCalledWith("75%", 68, 252);

  fireEvent.keyDown(document, { key: "Escape" });
  expect(onClose).toHaveBeenCalledOnce();
});
