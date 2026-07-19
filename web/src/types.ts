export type ToneId = "ngang" | "huyen" | "sac" | "hoi" | "nga" | "nang";

export type Accent = "north" | "south";

export type ToneFamilyId = "level" | "falling" | "rising" | "dipping";

export type ContourFeatures = {
  start: number;
  end: number;
  slope: number;
  curvature: number;
  pitch_range: number;
  minimum: number;
  dip_position: number;
  recovery: number;
  final_rise: number;
  duration_s: number;
  voiced_fraction: number;
  longest_voicing_gap_ms: number;
  central_rms_dip: number;
  terminal_energy_drop: number;
};

export type ClassifierTemplate = {
  id: string;
  word_id: string;
  tone: ToneId;
  accent: Accent;
  contour: number[];
  features: ContourFeatures;
  validated: boolean;
  source_path?: string;
};

export type ClassifierProfile = {
  version: string;
  manifest_hash: string;
  accent: Accent;
  scoring_mode: "six_tone" | "four_family";
  temperature: number;
  abstention_threshold: number;
  minimum_margin: number;
  feature_scales: number[];
  corpus_complete: boolean;
  missing_target_ids: string[];
  templates: ClassifierTemplate[];
};

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

export type MinimalPairForm = {
  tone: ToneId;
  surface: string;
  word_id: string | null;
  meaning_en: string | null;
};

export type MinimalPairGroup = {
  id: string;
  ascii_base: string;
  title: string;
  forms: MinimalPairForm[];
};

export type WordsPayload = {
  tones: Tone[];
  words: Word[];
  featured_queue: string[];
  drills?: Record<string, { id: string; title: string; word_ids: string[] }>;
  scoring_modes: Record<Accent, "six_tone" | "four_family" | string>;
  classifier_profiles?: Partial<Record<Accent, ClassifierProfile>>;
  minimal_pair_groups?: MinimalPairGroup[];
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

export type SemanticStatus =
  | "exact_correct"
  | "family_correct"
  | "family_ambiguous"
  | "wrong_known_word"
  | "wrong_no_known_word"
  | "uncertain";

export type MeaningVerdict = {
  status: SemanticStatus;
  assertion_level: "exact" | "family" | "none";
  detected_surface: string | null;
  detected_meaning_en: string | null;
  detected_word_id: string | null;
  tone_mark_label: string;
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
  semantic_status: SemanticStatus;
  class_confidence: number;
  signal_confidence: number;
  meaning_verdict: MeaningVerdict;
  classifier_version: string;
  classifier_manifest_hash: string;
};

export type CoachResult = {
  observation?: string;
  coaching_sentence: string;
  next_word: string;
  rationale: string;
  source: "gpt-5.6-sol" | "rules";
  refinement_status?:
    | "complete"
    | "cache_hit"
    | "no_key"
    | "rate_limited"
    | "daily_paused"
    | "busy"
    | "timeout"
    | "failed";
  fallback_reason?: string | null;
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
    paid_guard_ready?: boolean;
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
