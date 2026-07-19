import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  MICROPHONE_PRIVACY_STORAGE_KEY,
  MICROPHONE_PRIVACY_VERSION,
  hasCurrentMicrophoneAcknowledgement,
  useMicrophonePrivacy,
} from "./useMicrophonePrivacy";

describe("microphone privacy acknowledgement", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("invalidates an acknowledgement when the disclosure version changes", () => {
    window.localStorage.setItem(MICROPHONE_PRIVACY_STORAGE_KEY, JSON.stringify({
      version: "older-notice",
      modes: { tone_shapes: { acknowledged_at: "2026-07-18T00:00:00.000Z" } },
    }));
    expect(hasCurrentMicrophoneAcknowledgement("tone_shapes")).toBe(false);

    window.localStorage.setItem(MICROPHONE_PRIVACY_STORAGE_KEY, JSON.stringify({
      version: MICROPHONE_PRIVACY_VERSION,
      modes: { tone_shapes: { acknowledged_at: "2026-07-19T00:00:00.000Z" } },
    }));
    expect(hasCurrentMicrophoneAcknowledgement("tone_shapes")).toBe(true);
    expect(hasCurrentMicrophoneAcknowledgement("dialogue")).toBe(false);
  });

  it("does not run the microphone action until the learner acknowledges", () => {
    const openMicrophone = vi.fn();
    const { result } = renderHook(() => useMicrophonePrivacy());

    act(() => result.current.requestMicrophoneAccess("tone_shapes", openMicrophone));
    expect(result.current.open).toBe(true);
    expect(result.current.intent).toBe("tone_shapes");
    expect(openMicrophone).not.toHaveBeenCalled();

    act(() => result.current.acknowledgeAndContinue());
    expect(openMicrophone).toHaveBeenCalledOnce();
    expect(result.current.open).toBe(false);
    expect(hasCurrentMicrophoneAcknowledgement("tone_shapes")).toBe(true);

    act(() => result.current.requestMicrophoneAccess("dialogue", openMicrophone));
    expect(openMicrophone).toHaveBeenCalledOnce();
    expect(result.current.open).toBe(true);
    expect(result.current.intent).toBe("dialogue");

    act(() => result.current.acknowledgeAndContinue());
    expect(openMicrophone).toHaveBeenCalledTimes(2);
    expect(hasCurrentMicrophoneAcknowledgement("dialogue")).toBe(true);

    act(() => result.current.requestMicrophoneAccess("tone_shapes", openMicrophone));
    expect(openMicrophone).toHaveBeenCalledTimes(3);
  });

  it("cancels a pending microphone action when the notice is dismissed", () => {
    const openMicrophone = vi.fn();
    const { result } = renderHook(() => useMicrophonePrivacy());

    act(() => result.current.requestMicrophoneAccess("dialogue", openMicrophone));
    act(() => result.current.close());
    expect(openMicrophone).not.toHaveBeenCalled();
    expect(result.current.open).toBe(false);
  });
});
