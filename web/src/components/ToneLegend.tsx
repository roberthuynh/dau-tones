import { pedagogicalContour } from "../fallbackData";
import type { Accent, Tone } from "../types";

type ToneLegendProps = {
  tones: Tone[];
  accent: Accent;
  activeTone?: string;
  onSelect?: (toneId: string) => void;
};

function miniPoints(contour: number[]): string {
  return contour
    .filter((_, index) => index % 4 === 0 || index === contour.length - 1)
    .map((value, index, values) => `${(index / Math.max(1, values.length - 1)) * 46 + 2},${17 - value * 2.5}`)
    .join(" ");
}
export function ToneLegend({ tones, accent, activeTone, onSelect }: ToneLegendProps) {
  return (
    <div className="tone-legend" aria-label="Vietnamese tone legend">
      {tones.map((tone) => (
        <button
          className={`tone-legend__item ${activeTone === tone.id ? "tone-legend__item--active" : ""}`}
          style={{ "--legend-color": tone.color } as React.CSSProperties}
          key={tone.id}
          type="button"
          onClick={() => onSelect?.(tone.id)}
          aria-pressed={activeTone === tone.id}
        >
          <svg viewBox="0 0 50 34" aria-hidden="true">
            <polyline points={miniPoints(pedagogicalContour(tone.id, accent))} fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>
            <strong>{tone.name_vi}</strong>
            <small>{tone.name_en}</small>
          </span>
        </button>
      ))}
    </div>
  );
}
