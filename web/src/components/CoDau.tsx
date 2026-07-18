import { contourAt } from "../lib/curve";
import { vowelShapeForWord, type VowelShape } from "../lib/vowel";
import { useReducedMotion } from "../hooks/useReducedMotion";
import type { ToneId } from "../types";

type CoDauProps = {
  contour: number[];
  tone: ToneId;
  word?: string;
  progress?: number;
  playing?: boolean;
  compact?: boolean;
};

const MOUTH_PATHS: Record<VowelShape, string> = {
  open: "M116 154c12 24 38 24 50 0-8 30-42 30-50 0Z",
  rounded: "M127 155c0-15 6-23 14-23s14 8 14 23-6 24-14 24-14-9-14-24Z",
  spread: "M112 154c18 13 41 13 58 0",
};

const CLOSE_MOUTH_PATHS: Record<VowelShape, string> = {
  open: "M21 30c12 25 47 25 59 0-8 32-51 32-59 0Z",
  rounded: "M38 34c0-17 6-27 13-27s13 10 13 27-6 28-13 28-13-11-13-28Z",
  spread: "M16 35c23 15 49 15 69 0",
};

const MOTION_CUES: Record<ToneId, string> = {
  ngang: "Keep your chin level",
  huyen: "Let your chin glide down",
  sac: "Lift your chin smoothly",
  hoi: "Dip, then gently recover",
  nga: "Rise with a brief catch",
  nang: "Drop low, then stop",
};

const MOUTH_CUES: Record<VowelShape, string> = {
  open: "Open your jaw and keep the vowel relaxed",
  rounded: "Round your lips forward and keep the center open",
  spread: "Keep your lips gently wide, never tense",
};

export function CoDau({ contour, tone, word = "a", progress = 0, playing = false, compact = false }: CoDauProps) {
  const reducedMotion = useReducedMotion();
  const pitch = contourAt(contour, reducedMotion ? 0.62 : progress);
  const angle = Math.max(-12, Math.min(12, -pitch * 3));
  const glottal = tone === "nga" || tone === "nang";
  const arrow = tone === "ngang" ? "→" : tone === "huyen" || tone === "nang" ? "↘" : tone === "sac" ? "↗" : tone === "hoi" ? "⌄" : "↗";
  const vowelShape = vowelShapeForWord(word);
  const motionCue = MOTION_CUES[tone];
  const mouthCue = MOUTH_CUES[vowelShape];

  return (
    <div
      className={`co-dau ${compact ? "co-dau--compact" : ""} ${playing ? "co-dau--playing" : ""}`}
      aria-label={`Cô Dấu demonstrates: ${motionCue}. ${mouthCue}.${glottal ? " Add a brief catch in your throat." : ""}`}
    >
      <div className="co-dau__portrait">
        <span className="co-dau__follow" aria-hidden="true">{playing ? "Mirror me now" : "Watch + mirror"}</span>
        <span className="co-dau__motion-arrow" aria-hidden="true">{arrow}</span>
        <svg viewBox="0 0 280 270" role="img" aria-label="Cô Dấu demonstrating the head and mouth movement">
          <defs>
            <linearGradient id="ao-dai" x1="0" y1="0" x2="1" y2="1">
              <stop stopColor="#ec6657" />
              <stop offset="1" stopColor="#9c3a45" />
            </linearGradient>
            <radialGradient id="face-light" cx="45%" cy="35%" r="70%">
              <stop stopColor="#f1c39b" />
              <stop offset="1" stopColor="#d69a73" />
            </radialGradient>
          </defs>
          <path d="M53 270c7-54 40-78 87-78s80 24 87 78H53Z" fill="url(#ao-dai)" />
          <path d="M116 196h48l13 39-37 29-37-29 13-39Z" fill="#d7a176" />
          <g className="co-dau__head" style={{ transform: `rotate(${angle}deg)` }}>
            <path d="M46 108C47 38 88 9 141 12c61 4 99 58 88 129-4 30-18 54-39 70H88c-27-21-44-57-42-103Z" fill="#17120f" />
            <ellipse cx="140" cy="116" rx="79" ry="91" fill="url(#face-light)" />
            <path d="M57 99C59 43 94 17 141 18c38 1 68 23 84 59-37-7-59-24-74-49-18 33-48 56-94 71Z" fill="#181310" />
            <path d="M92 104c11-7 23-7 34 0M155 104c11-7 23-7 34 0" stroke="#2a1b16" strokeWidth="4" strokeLinecap="round" />
            <g className="co-dau__eyes">
              <ellipse cx="109" cy="115" rx="5" ry="7" fill="#241711" />
              <ellipse cx="172" cy="115" rx="5" ry="7" fill="#241711" />
            </g>
            <path d="M139 119c-5 14-4 24 5 26" stroke="#b97860" strokeWidth="3.5" strokeLinecap="round" />
            <circle className="co-dau__mouth-focus" cx="141" cy="158" r="34" />
            <path
              className="co-dau__mouth"
              data-vowel-shape={vowelShape}
              d={MOUTH_PATHS[vowelShape]}
              fill={vowelShape === "spread" ? "none" : "rgba(129, 52, 63, 0.34)"}
              stroke="#8f3b49"
              strokeWidth="6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path d="M65 85c-15 31-13 77 2 113" stroke="#17120f" strokeWidth="17" strokeLinecap="round" />
            <path d="M216 78c17 34 16 83 0 122" stroke="#17120f" strokeWidth="17" strokeLinecap="round" />
          </g>
          <circle className={`co-dau__throat ${glottal && playing ? "co-dau__throat--active" : ""}`} cx="140" cy="216" r="8" />
        </svg>
        {reducedMotion ? <span className="co-dau__arrow" aria-hidden="true">{arrow}</span> : null}
      </div>

      <div className="co-dau__lesson">
        <div className="co-dau__lesson-heading">
          <span className="co-dau__name">Cô Dấu</span>
          <strong>{motionCue}</strong>
        </div>
        <div className="co-dau__mechanics">
          <div className="co-dau__mouth-closeup" aria-label={`Mouth cue: ${mouthCue}`}>
            <svg viewBox="0 0 100 70" aria-hidden="true">
              <path
                className="co-dau__mouth"
                d={CLOSE_MOUTH_PATHS[vowelShape]}
                fill={vowelShape === "spread" ? "none" : "rgba(145, 63, 72, 0.25)"}
                stroke="currentColor"
                strokeWidth="5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span><i>mouth</i>{mouthCue}</span>
          </div>
          {glottal ? (
            <div className="co-dau__throat-closeup">
              <span className="co-dau__throat-ring"><i /></span>
              <span><i>throat</i>Catch briefly, then release</span>
            </div>
          ) : null}
        </div>
        <span className="co-dau__play-hint">{playing ? "Follow her head, lips, and throat" : "Press Listen + watch, then mirror her"}</span>
      </div>
    </div>
  );
}
