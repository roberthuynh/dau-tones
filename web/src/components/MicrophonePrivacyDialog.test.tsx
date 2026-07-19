import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MicrophonePrivacyDialog } from "./MicrophonePrivacyDialog";

it("explains local word grading and keyed Dialogue transcription before consent", () => {
  const acknowledge = vi.fn();
  render(
    <MicrophonePrivacyDialog
      open
      intent="dialogue"
      liveTranscription
      onAcknowledge={acknowledge}
      onClose={vi.fn()}
    />,
  );

  expect(screen.getByRole("dialog", { name: "Your voice stays under your control." })).toBeTruthy();
  expect(screen.queryByText("Tone Shapes stays on this device")).toBeNull();
  expect(screen.getByText("Dialogue transcription is on")).toBeTruthy();
  expect(screen.getByText(/gpt-4o-transcribe/)).toBeTruthy();
  expect(screen.getByText(/retains neither the audio nor the transcript/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "I understand · open microphone" }));
  expect(acknowledge).toHaveBeenCalledOnce();
});

it("opens as a review-only disclosure from the persistent Privacy control", () => {
  const close = vi.fn();
  render(
    <MicrophonePrivacyDialog
      open
      intent={null}
      liveTranscription={false}
      onAcknowledge={vi.fn()}
      onClose={close}
    />,
  );

  expect(screen.queryByRole("button", { name: /open microphone/i })).toBeNull();
  expect(screen.getByText("Tone Shapes stays on this device")).toBeTruthy();
  expect(screen.getByText("Dialogue stays local without a key")).toBeTruthy();
  expect(screen.getByText(/No OpenAI key is active, so your Dialogue recording is not uploaded/)).toBeTruthy();
  fireEvent.click(screen.getByText("Learn more about OpenAI API data handling"));
  expect(screen.getByText(/not used to train models by default/)).toBeTruthy();
  expect(screen.getByText(/up to 30 days/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Done" }));
  expect(close).toHaveBeenCalledOnce();
});
