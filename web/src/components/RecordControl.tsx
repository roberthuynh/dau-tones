import { MicIcon } from "./Icons";

type RecordControlProps = {
  state: "idle" | "requesting" | "recording" | "processing";
  level: number;
  elapsedMs: number;
  onToggle: () => void;
  label?: string;
};

export function RecordControl({ state, level, elapsedMs, onToggle, label = "Say it" }: RecordControlProps) {
  const recording = state === "recording";
  const busy = state === "requesting" || state === "processing";
  const scale = 1 + level * 0.26;
  return (
    <div className="record-control">
      <button
        type="button"
        className={`record-button ${recording ? "record-button--live" : ""}`}
        style={{ "--mic-scale": scale } as React.CSSProperties}
        onClick={onToggle}
        disabled={busy}
        aria-label={recording ? "Stop recording" : label}
        aria-pressed={recording}
      >
        <span className="record-button__meter" aria-hidden="true" />
        <span className="record-button__core">
          <MicIcon />
        </span>
      </button>
      <div className="record-control__copy" aria-live="polite">
        <strong>{recording ? "Listening" : state === "requesting" ? "Opening mic" : state === "processing" ? "Reading your pitch" : label}</strong>
        <span>{recording ? `${(elapsedMs / 1000).toFixed(1)}s · tap to stop` : busy ? "one moment" : "tap, speak once, then watch the curve"}</span>
      </div>
    </div>
  );
}
