import { useCallback, useEffect, useRef, useState } from "react";

export function useAudioPlayback() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const ownedUrlRef = useRef<string | null>(null);
  const frameRef = useRef<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const stop = useCallback(() => {
    if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    frameRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    if (ownedUrlRef.current) URL.revokeObjectURL(ownedUrlRef.current);
    ownedUrlRef.current = null;
    setPlaying(false);
    setProgress(0);
  }, []);

  const play = useCallback(
    async (source: string) => {
      stop();
      setError(null);
      const audio = new Audio(source);
      if (source.startsWith("blob:")) ownedUrlRef.current = source;
      audio.preload = "auto";
      audioRef.current = audio;
      audio.addEventListener("ended", () => {
        setPlaying(false);
        setProgress(1);
      }, { once: true });
      audio.addEventListener("error", () => {
        setError("That reference audio is unavailable. The target curve is still ready to follow.");
        setPlaying(false);
      }, { once: true });
      const tick = () => {
        if (!audio.paused && Number.isFinite(audio.duration) && audio.duration > 0) {
          setProgress(Math.min(1, audio.currentTime / audio.duration));
          frameRef.current = requestAnimationFrame(tick);
        }
      };
      try {
        await audio.play();
        setPlaying(true);
        frameRef.current = requestAnimationFrame(tick);
      } catch {
        setError("Your browser blocked playback. Tap play once more to allow audio.");
      }
    },
    [stop],
  );

  useEffect(() => stop, [stop]);

  return { play, stop, playing, progress, error, clearError: () => setError(null) };
}
