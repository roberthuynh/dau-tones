import { MicIcon } from "./Icons";

type RecordControlProps = {
  state: "idle" | "requesting" | "recording" | "processing";
  level: number;
  elapsedMs: number;
  onToggle: () => void;
  label?: string;
  idleHint?: string;
  processingLabel?: string;
  processingHint?: string;
  disabled?: boolean;
  disabledHint?: string;
};

export function RecordControl({
  state,
  level,
  elapsedMs,
  onToggle,
  label = "Record your tone",
  idleHint = "Tap once, say the word, then pause",
  processingLabel = "Reading your pitch",
  processingHint = "Mapping your voice against 64 pitch points",
  disabled = false,
  disabledHint = "A validated reference recording is needed first",
}: RecordControlProps) {
  const recording = state === "recording";
  const busy = state === "requesting" || state === "processing";
  const scale = 1 + level * 0.26;
  const stateLabel = disabled ? "Reference pending" : recording ? "Recording now" : state === "requesting" ? "Opening microphone" : state === "processing" ? processingLabel : label;
  const stateHint = recording
    ? `${(elapsedMs / 1000).toFixed(1)}s · tap to finish early`
    : state === "requesting"
      ? "Allow microphone access in your browser"
      : state === "processing"
        ? processingHint
        : disabled
          ? disabledHint
          : idleHint;

  return (
    <div className={`record-control record-control--${state}`} aria-busy={busy}>
      <button
        type="button"
        className={`record-button ${recording ? "record-button--live" : ""}`}
        style={{ "--mic-scale": scale } as React.CSSProperties}
        onClick={onToggle}
        disabled={busy || disabled}
        aria-label={recording ? "Stop recording" : stateLabel}
        aria-pressed={recording}
      >
        <span className="record-button__meter" aria-hidden="true" />
        <span className="record-button__core">
          {state === "processing" ? <span className="record-button__spinner" aria-hidden="true" /> : recording ? <span className="record-button__stop" aria-hidden="true" /> : <MicIcon />}
        </span>
      </button>
      <div className="record-control__copy" aria-live="polite">
        <small>{state === "idle" ? "Step 2 · your turn" : state === "processing" ? "Deterministic DSP" : "Microphone"}</small>
        <strong>{stateLabel}</strong>
        <span>{stateHint}</span>
      </div>
    </div>
  );
}
