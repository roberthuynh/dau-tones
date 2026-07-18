export type FeedbackSound = "correct" | "wrong" | "ambiguous";

const STORAGE_KEY = "dau-sound-v1";

export function loadSoundPreference(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "off";
  } catch {
    return true;
  }
}

export function saveSoundPreference(enabled: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, enabled ? "on" : "off");
  } catch {
    // Private browsing can disable storage; sound still works for this visit.
  }
}

export function playFeedbackSound(kind: FeedbackSound, enabled: boolean): void {
  if (!enabled || typeof window === "undefined") return;
  const Context = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Context) return;
  try {
    const context = new Context();
    const startedAt = context.currentTime + 0.015;
    const frequencies = kind === "correct" ? [523.25, 659.25, 783.99] : kind === "wrong" ? [440, 329.63] : [392];
    const noteLength = kind === "correct" ? 0.075 : 0.11;
    frequencies.forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const start = startedAt + index * noteLength * 0.82;
      oscillator.type = kind === "wrong" ? "triangle" : "sine";
      oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(kind === "ambiguous" ? 0.055 : 0.075, start + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + noteLength);
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + noteLength + 0.02);
    });
    window.setTimeout(() => void context.close(), 750);
  } catch {
    // Audio feedback is additive. Visual verdicts remain complete if it is blocked.
  }
}
