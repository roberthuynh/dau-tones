import type { Accent, Tone, ToneId, Word } from "../types";
import { TONE_ORDER } from "../lib/toneLanguage";
import { ToneSyllable } from "./ToneSyllable";

type MaToneRailProps = {
  words: Word[];
  tones: Tone[];
  accent: Accent;
  activeWordId: string;
  onSelect: (wordId: string) => void;
};

function miniPoints(contour: number[]): string {
  const sampled = contour.filter((_, index) => index % 4 === 0 || index === contour.length - 1);
  return sampled
    .map((value, index) => `${2 + (index / Math.max(1, sampled.length - 1)) * 47},${16 - value * 2.1}`)
    .join(" ");
}

export function MaToneRail({ words, tones, accent, activeWordId, onSelect }: MaToneRailProps) {
  const maWords = TONE_ORDER.map((toneId) => words.find((word) => word.id.startsWith("ma-") && word.tone === toneId)).filter(
    (word): word is Word => Boolean(word),
  );

  return (
    <nav className="ma-tone-rail" aria-label="The six tones of ma">
      <div className="ma-tone-rail__intro">
        <strong>One sound.</strong>
        <span>Six meanings.</span>
      </div>
      <div className="ma-tone-rail__items">
        {maWords.map((word) => {
          const tone = tones.find((item) => item.id === word.tone)!;
          const active = activeWordId === word.id;
          return (
            <button
              type="button"
              className={`ma-tone-choice ${active ? "ma-tone-choice--active" : ""}`}
              style={{ "--rail-tone": tone.color } as React.CSSProperties}
              onClick={() => onSelect(word.id)}
              aria-pressed={active}
              key={word.id}
            >
              <ToneSyllable text={word.syllable} tone={word.tone as ToneId} />
              <span className="ma-tone-choice__meta">
                <strong>{tone.name_vi}</strong>
                <small>{word.meaning_en}</small>
              </span>
              <svg viewBox="0 0 52 32" aria-hidden="true">
                <polyline
                  points={miniPoints(word.targets[accent].contour)}
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
