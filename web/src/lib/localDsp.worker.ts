import type { ClassifierProfile } from "../types";
import { analyzePcm, DspSignalError, type DspAnalysis } from "./dspCore";

export type LocalDspWorkerRequest = {
  id: number;
  samples: ArrayBuffer;
  sampleRate: number;
  profile: ClassifierProfile;
};

export type LocalDspWorkerResponse =
  | { id: number; ok: true; analysis: DspAnalysis }
  | {
      id: number;
      ok: false;
      error: { code: string; message: string; details: Record<string, string | number> };
    };

self.onmessage = (event: MessageEvent<LocalDspWorkerRequest>) => {
  const { id, samples, sampleRate, profile } = event.data;
  try {
    const analysis = analyzePcm(new Float32Array(samples), sampleRate, profile);
    const response: LocalDspWorkerResponse = { id, ok: true, analysis };
    self.postMessage(response);
  } catch (error) {
    const resolved =
      error instanceof DspSignalError
        ? error
        : new DspSignalError(
            "analysis_failed",
            error instanceof Error ? error.message : "The recording could not be analyzed.",
          );
    const response: LocalDspWorkerResponse = {
      id,
      ok: false,
      error: {
        code: resolved.code,
        message: resolved.message,
        details: resolved.details,
      },
    };
    self.postMessage(response);
  }
};

export {};
