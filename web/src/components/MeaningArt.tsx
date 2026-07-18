import { useState } from "react";
import type { Word } from "../types";

const FALLBACK_GLYPHS: Record<string, string> = {
  "phuong-name": "P",
  "phuong-ward": "⌂",
  "phuong-phoenix": "✦",
  "ma-ghost": "◌",
  "ma-but": "↔",
  "ma-mother": "♥",
  "ma-grave": "▱",
  "ma-code": "⌘",
  "ma-seedling": "⌁",
};

type MeaningArtProps = {
  word: Word;
  className?: string;
  eager?: boolean;
};

export function MeaningArt({ word, className = "", eager = false }: MeaningArtProps) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className={`meaning-art meaning-art--fallback tone-bg-${word.tone} ${className}`} role="img" aria-label={`Illustration placeholder for ${word.meaning_en}`}>
        <span>{FALLBACK_GLYPHS[word.id] ?? word.syllable.slice(0, 1).toUpperCase()}</span>
      </div>
    );
  }
  return (
    <div className={`meaning-art ${className}`}>
      <img src={word.art_url} alt={`Illustration of ${word.meaning_en}`} loading={eager ? "eager" : "lazy"} onError={() => setFailed(true)} />
    </div>
  );
}
