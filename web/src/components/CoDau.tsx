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
  open: "M78 97c7 12 20 12 27 0c-4 12-23 12-27 0Z",
  rounded: "M84 99c0-7 4-11 9-11s9 4 9 11-4 11-9 11-9-4-9-11Z",
  spread: "M77 98c10 7 23 7 32 0",
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
  open: "Open your jaw and relax",
  rounded: "Round your lips forward",
  spread: "Keep your lips gently wide",
};

export function CoDau({ contour, tone, word = "a", progress = 0, playing = false, compact = false }: CoDauProps) {
  const reducedMotion = useReducedMotion();
  const pitch = contourAt(contour, reducedMotion ? 0.62 : progress);
  const angle = Math.max(-13, Math.min(13, -pitch * 3.1));
  const glottal = tone === "nga" || tone === "nang";
  const arrow = tone === "ngang" ? "→" : tone === "huyen" || tone === "nang" ? "↘" : tone === "sac" ? "↗" : tone === "hoi" ? "⌄" : "↗";
  const vowelShape = vowelShapeForWord(word);
  const motionCue = MOTION_CUES[tone];
  const mouthCue = MOUTH_CUES[vowelShape];

  return (
    <div
      className={`co-dau ${compact ? "co-dau--compact" : ""} ${playing ? "co-dau--playing" : ""}`}
      aria-label={`Cô Dấu: ${motionCue}. ${mouthCue}.${glottal ? " Feel the catch in your throat." : ""}`}
    >
      <div className="co-dau__portrait">
        <span className="co-dau__follow" aria-hidden="true">{playing ? "Mirror me now" : "Watch + mirror"}</span>
        <span className="co-dau__motion-arrow" aria-hidden="true">{arrow}</span>
        <svg viewBox="0 0 180 210" role="img" aria-hidden="true">
          <defs>
            <linearGradient id="ao-dai" x1="0" y1="0" x2="1" y2="1">
              <stop stopColor="#e85e50" />
              <stop offset="1" stopColor="#a63f45" />
            </linearGradient>
          </defs>
          <path d="M45 209c3-48 19-70 45-70s42 22 45 70H45Z" fill="url(#ao-dai)" />
          <path d="M76 142h28l7 35-21 18-21-18 7-35Z" fill="#d8a77c" />
          <g className="co-dau__head" style={{ transform: `rotate(${angle}deg)` }}>
            <path d="M50 61c3-37 26-52 49-48 28 5 41 31 32 65-4 15-12 24-21 31H68c-14-10-21-28-18-48Z" fill="#17120f" />
            <ellipse cx="90" cy="73" rx="39" ry="48" fill="#e0b189" />
            <path d="M52 66c2-36 23-52 48-50 19 2 31 13 38 31-14-3-25-10-32-20-9 18-27 30-54 39Z" fill="#181310" />
            <path d="M72 71c5-3 10-3 15 0M100 71c5-3 10-3 15 0" stroke="#2a1b16" strokeWidth="2.4" strokeLinecap="round" />
            <g className="co-dau__eyes">
              <ellipse cx="79" cy="77" rx="2.2" ry="3.2" fill="#241711" />
              <ellipse cx="108" cy="77" rx="2.2" ry="3.2" fill="#241711" />
            </g>
            <path d="M91 79c-2 6-2 10 2 11" stroke="#bc8067" strokeWidth="1.8" strokeLinecap="round" />
            <circle className="co-dau__mouth-focus" cx="93" cy="101" r="18" />
            <path
              className="co-dau__mouth"
              data-vowel-shape={vowelShape}
              d={MOUTH_PATHS[vowelShape]}
              fill={vowelShape === "spread" ? "none" : "rgba(158, 75, 80, 0.3)"}
              stroke="#913f48"
              strokeWidth="3.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path d="M59 62c-6 11-7 30-1 47" stroke="#17120f" strokeWidth="9" strokeLinecap="round" />
            <path d="M126 56c8 13 8 35 1 54" stroke="#17120f" strokeWidth="9" strokeLinecap="round" />
          </g>
          <circle className={`co-dau__throat ${glottal && playing ? "co-dau__throat--active" : ""}`} cx="90" cy="140" r="5" />
        </svg>
        {reducedMotion ? <span className="co-dau__arrow" aria-hidden="true">{arrow}</span> : null}
      </div>
      <div className="co-dau__lesson">
        <span className="co-dau__name">Cô Dấu</span>
        <strong>{motionCue}</strong>
        <span className="co-dau__lip-cue"><i>mouth</i>{mouthCue}</span>
        {glottal ? <span className="co-dau__throat-cue"><i>throat</i>Feel the brief catch</span> : null}
        <span className="co-dau__play-hint">{playing ? "Follow her head and lips" : "Press “Listen + watch” below"}</span>
      </div>
    </div>
  );
}
