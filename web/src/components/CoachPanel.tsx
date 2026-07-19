import { toneById, wordById } from "../fallbackData";
import type { CoachResult, Word, WordsPayload } from "../types";
import { ArrowIcon, SparkIcon } from "./Icons";

export type RichCoach = CoachResult & { observation?: string };
export type CoachRefinementStatus = "local" | "refining" | "complete" | "unavailable";

type CoachPanelProps = {
  coach: RichCoach | null;
  refinementStatus: CoachRefinementStatus;
  currentWord: Word;
  payload: WordsPayload;
  onNext: () => void;
  onUseInDialogue?: (wordId: string) => void;
};

export function CoachPanel({ coach, refinementStatus, currentWord, payload, onNext, onUseInDialogue }: CoachPanelProps) {
  const next = wordById(coach?.next_word, payload.words) ?? currentWord;
  const refinementLabel = refinementStatus === "refining"
    ? "GPT-5.6 is refining this cue"
    : refinementStatus === "complete"
      ? "GPT-5.6 refined coach"
      : refinementStatus === "unavailable"
        ? "Instant coach · AI refinement unavailable"
        : "Instant local coach";
  return (
    <section className="coach-decision" aria-busy={refinementStatus === "refining"}>
      <div className={`coach-decision__label coach-decision__label--${refinementStatus}`} role="status">
        {refinementStatus === "refining" ? <span className="coach-decision__spinner" aria-hidden="true" /> : <SparkIcon />}
        {refinementLabel}
      </div>
      {refinementStatus === "refining" ? <p className="coach-decision__refinement">Your measured cue is ready now. The AI wording and next drill are updating in the background.</p> : null}
      {refinementStatus === "unavailable" ? <p className="coach-decision__refinement">The measured local cue stays active, so you can keep practicing without waiting.</p> : null}
      {coach?.observation ? <p className="coach-decision__observation">{coach.observation}</p> : null}
      <p className="coach-decision__instruction">{coach?.coaching_sentence ?? toneById(currentWord.tone, payload.tones).physical_cue}</p>
      <button type="button" className="next-decision" onClick={onNext}>
        <span>Next shape</span>
        <strong>{next.syllable}</strong>
        <small>{coach?.rationale ?? "Repeat the closest contrast while the movement is fresh."}</small>
        <ArrowIcon />
      </button>
      {onUseInDialogue ? <button type="button" className="coach-decision__dialogue" onClick={() => onUseInDialogue(currentWord.id)}>Use this tone in Dialogue Practice <ArrowIcon /></button> : null}
    </section>
  );
}
