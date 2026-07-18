import type { ToneId } from "../types";

const TONE_MARKS = new Set(["\u0300", "\u0301", "\u0303", "\u0309", "\u0323"]);
const VIETNAMESE_SEGMENTER = new Intl.Segmenter("vi", { granularity: "grapheme" });

type ToneSyllableProps = {
  text: string;
  tone: ToneId;
  className?: string;
};

export function ToneSyllable({ text, tone, className = "" }: ToneSyllableProps) {
  const segments = Array.from(VIETNAMESE_SEGMENTER.segment(text), ({ segment }) => segment);
  return (
    <span className={`tone-syllable tone-text-${tone} ${className}`} lang="vi">
      {segments.map((segment, index) => {
        const carriesTone = Array.from(segment.normalize("NFD")).some((character) => TONE_MARKS.has(character));
        return (
          <span className={carriesTone || tone === "ngang" ? "tone-syllable__voiced" : "tone-syllable__plain"} key={`${segment}-${index}`}>
            {segment}
          </span>
        );
      })}
    </span>
  );
}
