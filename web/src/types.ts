export type ToneId = "ngang" | "huyen" | "sac" | "hoi" | "nga" | "nang";

export type Accent = "north" | "south";

export type ToneFamilyId = "level" | "falling" | "rising" | "dipping";

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

export type AnalysisWord = {
  id: string;
  surface: string;
  meaning_en: string;
  art_url: string;
};

export type AnalysisAlternative = {
  tone: ToneId;
  family: ToneFamilyId;
  score: number;
  confidence: number;
};

export type SignalQuality = {
  peak: number;
  rms: number;
  clipping_fraction: number;
  active_duration_s: number;
  total_duration_s: number;
  voiced_fraction: number;
  longest_voicing_gap_ms: number;
  island_count: number;
};

export type RetrySignalQuality = {
  code: string;
  message: string;
  details?: Record<string, string | number>;
};

export type AnalysisResult = {
  tone_detected: ToneId;
  tone_intended: ToneId;
  detected_word_id: string | null;
  intended_word_id: string;
  correct: boolean;
  confidence: number;
  learner_contour: number[];
  target_contour: number[];
  detected_contour: number[] | null;
  tips_features: {
    codes: string[];
    numeric: Record<string, number>;
  };
  grading_mode: "six_tone" | "four_family";
  exact_verified: boolean;
  family_verified: boolean;
  alternatives: AnalysisAlternative[];
  needs_retry: boolean;
  signal_quality: SignalQuality | RetrySignalQuality;
  tone_family: ToneFamilyId;
  intended_family: ToneFamilyId;
  exact_tone_match: boolean;
  family_correct: boolean;
  verification_level: "exact" | "family" | "uncertain";
  tone_alternatives: Array<{
    tone: ToneId;
    family: ToneFamilyId;
    score: number;
    probability: number;
  }>;
  word: string;
  intended_word: AnalysisWord;
  detected_word: AnalysisWord | null;
  verdict_copy: string | null;
  target_validated: boolean;
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
  focus_word_ids?: string[];
  shadow_audio?: Record<Accent, string>;
  audio_urls?: Record<Accent, string>;
  literal_stakes?: Array<{
    target_token: string;
    heard_token: string;
    intended_word_id: string;
    heard_word_id: string;
    explanation: string;
  }>;
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
  sentence_id: string;
  transcript: string;
  target_text: string;
  tokens: EchoDiffToken[];
  explanation: string;
  literal_explanation: string;
  reveal_id: string | null;
  source: string;
  target: string;
  diff: EchoDiffToken[];
};

export type DemoId = "phuong-ward" | "ma-ghost" | "ma-correct";
