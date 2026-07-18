import { useCallback, useEffect, useRef, useState } from "react";

type RecorderState = "idle" | "requesting" | "recording" | "processing";

type RecorderOptions = {
  onRecording: (blob: Blob) => void | Promise<void>;
  minimumMs?: number;
  silenceMs?: number;
  hardStopMs?: number;
};

type RecorderApi = {
  state: RecorderState;
  level: number;
  elapsedMs: number;
  error: string | null;
  toggle: () => void;
  start: () => Promise<void>;
  stop: () => void;
  clearError: () => void;
};

function preferredMimeType(): string | undefined {
  const options = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"];
  return options.find((mime) => window.MediaRecorder?.isTypeSupported(mime));
}

export function useRecorder({ onRecording, minimumMs = 350, silenceMs = 800, hardStopMs = 6_000 }: RecorderOptions): RecorderApi {
  const [state, setState] = useState<RecorderState>("idle");
  const [level, setLevel] = useState(0);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const contextRef = useRef<AudioContext | null>(null);
  const frameRef = useRef<number | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const startedAtRef = useRef(0);
  const lastVoiceAtRef = useRef(0);
  const speechSeenRef = useRef(false);
  const callbackRef = useRef(onRecording);

  useEffect(() => {
    callbackRef.current = onRecording;
  }, [onRecording]);

  const release = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void contextRef.current?.close();
    contextRef.current = null;
    recorderRef.current = null;
    setLevel(0);
  }, []);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === "inactive") return;
    setState("processing");
    recorder.stop();
  }, []);

  const start = useCallback(async () => {
    if (state !== "idle") return;
    setError(null);
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setError("This browser cannot record audio. Use a current Chrome, Safari, or Edge, or try a sample.");
      return;
    }
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false },
      });
      streamRef.current = stream;
      const mimeType = preferredMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;
      chunksRef.current = [];
      recorder.addEventListener("dataavailable", (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      });
      recorder.addEventListener("stop", () => {
        const duration = performance.now() - startedAtRef.current;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || mimeType || "audio/webm" });
        release();
        if (duration < minimumMs || blob.size < 700) {
          setError("That was too short to hear a tone. Hold the vowel for one comfortable beat.");
          setState("idle");
          return;
        }
        Promise.resolve(callbackRef.current(blob))
          .catch(() => undefined)
          .finally(() => setState("idle"));
      });

      const audioContext = new AudioContext();
      contextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024;
      analyser.smoothingTimeConstant = 0.68;
      source.connect(analyser);
      const samples = new Float32Array(analyser.fftSize);

      startedAtRef.current = performance.now();
      lastVoiceAtRef.current = startedAtRef.current;
      speechSeenRef.current = false;
      recorder.start(120);
      setElapsedMs(0);
      setState("recording");

      let lastRenderAt = 0;
      const monitor = (now: number) => {
        analyser.getFloatTimeDomainData(samples);
        let squareSum = 0;
        for (let index = 0; index < samples.length; index += 1) squareSum += samples[index] * samples[index];
        const rms = Math.sqrt(squareSum / samples.length);
        const elapsed = now - startedAtRef.current;
        if (rms > 0.032) {
          speechSeenRef.current = true;
          lastVoiceAtRef.current = now;
        }
        if (now - lastRenderAt > 34) {
          setLevel(Math.min(1, rms * 11));
          setElapsedMs(elapsed);
          lastRenderAt = now;
        }
        if (elapsed >= hardStopMs || (speechSeenRef.current && elapsed >= minimumMs && now - lastVoiceAtRef.current >= silenceMs)) {
          stop();
          return;
        }
        frameRef.current = requestAnimationFrame(monitor);
      };
      frameRef.current = requestAnimationFrame(monitor);
    } catch (cause) {
      release();
      const denied = cause instanceof DOMException && (cause.name === "NotAllowedError" || cause.name === "PermissionDeniedError");
      setError(denied ? "Microphone access is off. Allow it in your browser, or use a sample to see the full loop." : "Dấu could not open the microphone. Check that another app is not using it.");
      setState("idle");
    }
  }, [hardStopMs, minimumMs, release, silenceMs, state, stop]);

  const toggle = useCallback(() => {
    if (state === "recording") stop();
    else if (state === "idle") void start();
  }, [start, state, stop]);

  useEffect(() => release, [release]);

  return {
    state,
    level,
    elapsedMs,
    error,
    toggle,
    start,
    stop,
    clearError: () => setError(null),
  };
}
