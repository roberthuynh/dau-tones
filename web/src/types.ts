export type ToneId = "ngang" | "huyen" | "sac" | "hoi" | "nga" | "nang";

export type Accent = "north" | "south";

export type Tone = {
  id: ToneId;
  name_vi: string;
  name_en: string;
  color: string;
  physical_cue: string;
};

export type TargetReference = {
  audio_url: string;
  contour: number[];
  validated: boolean;
};

export type Word = {
  id: string;
  syllable: string;
  surface?: string;
  tone: ToneId;
  meaning_en: string;
  usage_note?: string;
  art_url: string;
  minimal_pair_ids?: string[];
  targets: Record<Accent, TargetReference>;
};

export type WordsPayload = {
  tones: Tone[];
  words: Word[];
  featured_queue: string[];
  drills?: Record<string, { id: string; title: string; word_ids: string[] }>;
  scoring_modes: Record<Accent, "six_tone" | "four_family" | string>;
};

export type AnalysisResult = {
  tone_detected: ToneId;
  tone_intended: ToneId;
  detected_word_id?: string;
  intended_word_id?: string;
  correct: boolean;
  confidence: number;
  learner_contour: number[];
  target_contour: number[];
  detected_contour?: number[];
  tips_features: Record<string, string | number | boolean>;
  grading_mode?: string;
  exact_verified?: boolean;
  family_verified?: boolean;
  alternatives?: Array<{ tone: ToneId; confidence: number }>;
  needs_retry?: boolean;
  signal_quality?: { label?: string; message?: string } | string;
};

export type CoachResult = {
  coaching_sentence: string;
  next_word: string;
  rationale: string;
  source: "gpt-5.6-sol" | "rules";
};

export type HealthPayload = {
  ready?: boolean;
  scoring_modes?: Record<Accent, string>;
  capabilities?: {
    ai_coaching?: boolean;
    live_echo_transcription?: boolean;
    cached_echo_speech?: boolean;
    echo_transcription?: boolean;
    echo_speech?: boolean;
    live_art?: boolean;
  };
};

export type SessionToneStat = { attempts: number; correct: number };

export type EchoSentence = {
  id: string;
  text: string;
  gloss_en: string;
  theme?: string;
  shadow_audio?: Record<Accent, string>;
};

export type EchoDiffToken = {
  target: string | null;
  heard: string | null;
  kind: "match" | "tone_only" | "lexical" | "missing" | "extra";
  target_word_id?: string | null;
  heard_word_id?: string | null;
  meaning_explanation?: string | null;
};

export type EchoResult = {
  transcript: string;
  target_text?: string;
  tokens?: EchoDiffToken[];
  diff?: EchoDiffToken[];
  explanation?: string;
  literal_explanation?: string;
  reveal_id?: string;
  reveal_art_url?: string;
  source?: string;
};

export type DemoId = "phuong-ward" | "ma-ghost" | "ma-correct";
