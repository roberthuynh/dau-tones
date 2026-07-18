import { useCallback, useEffect, useRef, useState } from "react";
import { getEchoSpeech } from "../../lib/api";
import type { EchoTurn } from "../../lib/echoCourse";
import type { Accent } from "../../types";

type PlaybackState = {
  playing: boolean;
  progress: number;
  turnId: string | null;
  error: string | null;
};

type PlayOptions = {
  allowApiFallback?: boolean;
};

export function useEchoTurnPlayback() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ownedUrlRef = useRef<string | null>(null);
  const frameRef = useRef<number | null>(null);
  const attemptRef = useRef(0);
  const [state, setState] = useState<PlaybackState>({ playing: false, progress: 0, turnId: null, error: null });

  const stop = useCallback(() => {
    attemptRef.current += 1;
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    audioRef.current = null;
    if (ownedUrlRef.current) URL.revokeObjectURL(ownedUrlRef.current);
    ownedUrlRef.current = null;
    setState((current) => ({ ...current, playing: false, progress: 0, turnId: null }));
  }, []);

  const playSource = useCallback(async (source: string, turnId: string, attempt: number): Promise<boolean> => {
    const audio = new Audio(source);
    if (source.startsWith("blob:")) ownedUrlRef.current = source;
    audio.preload = "auto";
    audioRef.current = audio;
    return new Promise<boolean>((resolve) => {
      let settled = false;
      const settle = (value: boolean) => {
        if (settled) return;
        settled = true;
        if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
        if (attempt === attemptRef.current) {
          setState((current) => ({ ...current, playing: false, progress: value ? 1 : current.progress }));
        }
        resolve(value);
      };
      const tick = () => {
        if (attempt !== attemptRef.current || audio.paused) return;
        if (Number.isFinite(audio.duration) && audio.duration > 0) {
          setState((current) => ({ ...current, progress: Math.min(1, audio.currentTime / audio.duration) }));
        }
        frameRef.current = requestAnimationFrame(tick);
      };
      audio.addEventListener("ended", () => settle(true), { once: true });
      audio.addEventListener("error", () => settle(false), { once: true });
      void audio.play().then(() => {
        if (attempt !== attemptRef.current) {
          audio.pause();
          settle(false);
          return;
        }
        setState({ playing: true, progress: 0, turnId, error: null });
        frameRef.current = requestAnimationFrame(tick);
      }).catch(() => settle(false));
    });
  }, []);

  const playTurn = useCallback(async (turn: EchoTurn, accent: Accent, options: PlayOptions = {}): Promise<boolean> => {
    stop();
    const attempt = attemptRef.current;
    setState({ playing: false, progress: 0, turnId: turn.id, error: null });
    const staticSource = turn.audio_urls[accent];
    if (staticSource && await playSource(staticSource, turn.id, attempt)) return true;
    if (attempt !== attemptRef.current || options.allowApiFallback === false) return false;
    try {
      const apiSource = await getEchoSpeech(turn.id, accent);
      if (attempt !== attemptRef.current) return false;
      if (apiSource !== staticSource && await playSource(apiSource, turn.id, attempt)) return true;
    } catch {
      // The learner can still read the partner bubble and continue without audio.
    }
    if (attempt === attemptRef.current) {
      setState({
        playing: false,
        progress: 0,
        turnId: turn.id,
        error: "Thầy Minh’s audio is unavailable. Read his line, then continue with your reply.",
      });
    }
    return false;
  }, [playSource, stop]);

  useEffect(() => stop, [stop]);

  return {
    ...state,
    playTurn,
    stop,
    clearError: () => setState((current) => ({ ...current, error: null })),
  };
}
