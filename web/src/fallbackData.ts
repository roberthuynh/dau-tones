import type {
  Accent,
  AnalysisResult,
  CoachResult,
  EchoResult,
  EchoSentence,
  Tone,
  ToneId,
  Word,
  WordsPayload,
} from "./types";

const COLORS: Record<ToneId, string> = {
  ngang: "#d8c7a0",
  huyen: "#5f86df",
  sac: "#ff6b5e",
  hoi: "#a98af4",
  nga: "#35c1b4",
  nang: "#f4a641",
};

export const TONES: Tone[] = [
  {
    id: "ngang",
    name_vi: "ngang",
    name_en: "level",
    color: COLORS.ngang,
    physical_cue: "Keep your chin still and carry the vowel straight across.",
  },
  {
    id: "huyen",
    name_vi: "huyền",
    name_en: "falling",
    color: COLORS.huyen,
    physical_cue: "Start comfortably and let your chin settle as the pitch falls.",
  },
  {
    id: "sac",
    name_vi: "sắc",
    name_en: "rising",
    color: COLORS.sac,
    physical_cue: "Start lower, lift your chin, and let the vowel rise cleanly.",
  },
  {
    id: "hoi",
    name_vi: "hỏi",
    name_en: "dipping",
    color: COLORS.hoi,
    physical_cue: "Let your chin dip through the middle, then recover slightly.",
  },
  {
    id: "nga",
    name_vi: "ngã",
    name_en: "broken rising",
    color: COLORS.nga,
    physical_cue: "Briefly catch the sound in your throat, then release it upward.",
  },
  {
    id: "nang",
    name_vi: "nặng",
    name_en: "low stopped",
    color: COLORS.nang,
    physical_cue: "Drop low, shorten the vowel, and stop it firmly in your throat.",
  },
];

export function pedagogicalContour(tone: ToneId, accent: Accent = "north"): number[] {
  return Array.from({ length: 64 }, (_, index) => {
    const x = index / 63;
    let y = 0;
    switch (tone) {
      case "ngang":
        y = 0.18 * Math.sin(Math.PI * x);
        break;
      case "huyen":
        y = 1.9 - 4 * x + 0.25 * Math.sin(Math.PI * x);
        break;
      case "sac":
        y = -2.1 + 5.2 * x ** 1.65;
        break;
      case "hoi":
        y = x < 0.62 ? 1.7 - 5.2 * Math.sin((Math.PI * x) / 1.22) : -1.4 + 5.3 * (x - 0.62);
        break;
      case "nga":
        if (accent === "south") {
          y = x < 0.58 ? 1.2 - 4 * Math.sin((Math.PI * x) / 1.16) : -1.35 + 5.2 * (x - 0.58);
        } else {
          y = -1 + 1.3 * x + 3 * Math.max(x - 0.46, 0) + (x > 0.43 && x < 0.54 ? -0.85 : 0);
        }
        break;
      case "nang":
        y = 1.2 - 4.2 * Math.min(x / 0.7, 1);
        break;
    }
    return Number(y.toFixed(4));
  });
}

const WORD_ROWS: Array<[string, string, ToneId, string, string]> = [
  ["phuong-name", "Phương", "ngang", "Phương, a woman's name", "phương can also mean direction"],
  ["phuong-ward", "phường", "huyen", "urban ward", "An administrative ward inside a Vietnamese city."],
  ["phuong-phoenix", "phượng", "nang", "phoenix", "Phượng names the phoenix and is also used as a given name."],
  ["ma-ghost", "ma", "ngang", "ghost", "The ordinary noun ma refers to a ghost or spirit."],
  ["ma-but", "mà", "huyen", "but / that", "A common connector meaning but, that, or which."],
  ["ma-mother", "má", "sac", "mother", "A warm everyday word for Mom in Southern Vietnamese."],
  ["ma-grave", "mả", "hoi", "grave", "A grave or burial place."],
  ["ma-code", "mã", "nga", "code", "A code or identifier."],
  ["ma-seedling", "mạ", "nang", "rice seedling", "A young rice plant ready for the paddy."],
  ["com-rice", "cơm", "ngang", "cooked rice / meal", "Cooked rice or a meal."],
  ["nha-home", "nhà", "huyen", "home / house", "A home, house, or household."],
  ["ca-fish", "cá", "sac", "fish", "Fish."],
  ["la-leaf", "lá", "sac", "leaf", "A leaf."],
  ["pho-noodle-soup", "phở", "hoi", "phở noodle soup", "Vietnamese rice noodle soup."],
  ["cua-door", "cửa", "hoi", "door", "A door or entrance."],
  ["sua-milk", "sữa", "nga", "milk", "Milk."],
  ["mu-hat", "mũ", "nga", "hat", "A hat."],
  ["me-mother", "mẹ", "nang", "mother", "The widely used Vietnamese word for mother."],
  ["ban-friend", "bạn", "nang", "friend", "A friend or peer."],
];

const MA_IDS = ["ma-ghost", "ma-but", "ma-mother", "ma-grave", "ma-code", "ma-seedling"];
const PHUONG_IDS = ["phuong-name", "phuong-ward", "phuong-phoenix"];
const MISSING_TARGETS = new Set([
  "south:ma-grave",
  "south:phuong-phoenix",
]);

export const FALLBACK_WORDS: Word[] = WORD_ROWS.map(([id, syllable, tone, meaning_en, usage_note]) => ({
  id,
  syllable,
  surface: syllable,
  tone,
  meaning_en,
  usage_note,
  art_url: `/art/${id}.png`,
  minimal_pair_ids: id.startsWith("ma-") ? MA_IDS.filter((value) => value !== id) : id.startsWith("phuong-") ? PHUONG_IDS.filter((value) => value !== id) : [],
  targets: {
    north: {
      audio_url: MISSING_TARGETS.has(`north:${id}`) ? "" : `/audio/targets/north/${id}.wav`,
      contour: pedagogicalContour(tone, "north"),
      validated: !MISSING_TARGETS.has(`north:${id}`),
    },
    south: {
      audio_url: MISSING_TARGETS.has(`south:${id}`) ? "" : `/audio/targets/south/${id}.wav`,
      contour: pedagogicalContour(tone, "south"),
      validated: !MISSING_TARGETS.has(`south:${id}`),
    },
  },
}));

export const FEATURED_QUEUE = [
  ...MA_IDS,
  ...PHUONG_IDS,
  ...WORD_ROWS.map(([id]) => id).filter((id) => !MA_IDS.includes(id) && !PHUONG_IDS.includes(id)),
];

export const FALLBACK_PAYLOAD: WordsPayload = {
  tones: TONES,
  words: FALLBACK_WORDS,
  featured_queue: FEATURED_QUEUE,
  scoring_modes: { north: "four_family", south: "four_family" },
  minimal_pair_groups: [
    {
      id: "ma-six-tones",
      ascii_base: "ma",
      title: "The six meanings of ma",
      forms: [
        { tone: "ngang", surface: "ma", word_id: "ma-ghost", meaning_en: "ghost" },
        { tone: "huyen", surface: "mà", word_id: "ma-but", meaning_en: "but / that" },
        { tone: "sac", surface: "má", word_id: "ma-mother", meaning_en: "mother" },
        { tone: "hoi", surface: "mả", word_id: "ma-grave", meaning_en: "grave" },
        { tone: "nga", surface: "mã", word_id: "ma-code", meaning_en: "code" },
        { tone: "nang", surface: "mạ", word_id: "ma-seedling", meaning_en: "rice seedling" },
      ],
    },
    {
      id: "phuong-six-tones",
      ascii_base: "phuong",
      title: "The Phương name test",
      forms: [
        { tone: "ngang", surface: "Phương", word_id: "phuong-name", meaning_en: "Phương, a woman's name" },
        { tone: "huyen", surface: "phường", word_id: "phuong-ward", meaning_en: "urban ward" },
        { tone: "sac", surface: "phướng", word_id: null, meaning_en: null },
        { tone: "hoi", surface: "phưởng", word_id: null, meaning_en: null },
        { tone: "nga", surface: "phưỡng", word_id: null, meaning_en: null },
        { tone: "nang", surface: "phượng", word_id: "phuong-phoenix", meaning_en: "phoenix" },
      ],
    },
  ],
  drills: {
    food: { id: "food", title: "At the table", word_ids: ["com-rice", "ca-fish", "pho-noodle-soup", "sua-milk", "ma-mother", "ma-ghost"] },
    family: { id: "family", title: "Names and family", word_ids: ["phuong-name", "phuong-ward", "phuong-phoenix", "ma-mother", "me-mother", "ban-friend", "nha-home"] },
    travel: { id: "travel", title: "Around town", word_ids: ["phuong-ward", "nha-home", "cua-door", "pho-noodle-soup", "com-rice", "ban-friend", "la-leaf"] },
  },
};

export const FALLBACK_ECHO_SENTENCES: EchoSentence[] = [
  { id: "xin-chao", text: "Xin chào!", gloss_en: "Hello!", theme: "greetings" },
  { id: "cam-on-ban", text: "Cảm ơn bạn.", gloss_en: "Thank you.", theme: "greetings" },
  { id: "ban-khoe-khong", text: "Bạn khỏe không?", gloss_en: "How are you?", theme: "greetings" },
  { id: "me-toi-ten-la-phuong", text: "Mẹ tôi tên là Phương.", gloss_en: "My mother's name is Phương.", theme: "family" },
  { id: "invite-mom-to-dinner", text: "Tối nay con mời má đi ăn cơm.", gloss_en: "Tonight, I'm inviting Mom to dinner.", theme: "family" },
  { id: "order-pho", text: "Cho tôi một tô phở.", gloss_en: "Please give me a bowl of phở.", theme: "food" },
  { id: "order-water", text: "Cho tôi một ly nước.", gloss_en: "Please give me a glass of water.", theme: "food" },
  { id: "find-restroom", text: "Nhà vệ sinh ở đâu?", gloss_en: "Where is the restroom?", theme: "travel" },
];

function variedContour(tone: ToneId, accent: Accent, variant: "close" | "flat" | "fall"): number[] {
  const base = pedagogicalContour(tone, accent);
  return base.map((value, index) => {
    const x = index / 63;
    if (variant === "flat") return Number((0.12 * Math.sin(x * Math.PI * 2) - 0.08).toFixed(3));
    if (variant === "fall") return Number((1.85 - 4.05 * x + 0.08 * Math.sin(x * 9)).toFixed(3));
    return Number((value + 0.13 * Math.sin(x * 13) - 0.04).toFixed(3));
  });
}

export function demoAnalysis(id: "phuong-ward" | "ma-ghost" | "ma-correct", accent: Accent): AnalysisResult {
  const intendedTone = id === "phuong-ward" ? "ngang" : "sac";
  const detectedTone: ToneId = id === "phuong-ward" ? "huyen" : id === "ma-ghost" ? "ngang" : "sac";
  const intendedWordId = id === "phuong-ward" ? "phuong-name" : "ma-mother";
  const detectedWordId = id === "phuong-ward" ? "phuong-ward" : id === "ma-ghost" ? "ma-ghost" : "ma-mother";
  const intendedWord = wordById(intendedWordId)!;
  const detectedWord = wordById(detectedWordId)!;
  const intendedFamily = intendedTone === "ngang" ? "level" : "rising";
  const detectedFamily = detectedTone === "ngang" ? "level" : detectedTone === "huyen" ? "falling" : "rising";
  const correct = id === "ma-correct";
  const confidence = correct ? 0.91 : 0.88;
  const tips = id === "phuong-ward" ? ["ended_too_low", "fell_instead_of_level"] : id === "ma-ghost" ? ["no_final_rise", "too_flat"] : [];
  const asAnalysisWord = (word: Word) => ({
    id: word.id,
    surface: word.syllable,
    meaning_en: word.meaning_en,
    art_url: word.art_url,
  });
  return {
    tone_detected: detectedTone,
    tone_intended: intendedTone,
    intended_word_id: intendedWordId,
    detected_word_id: detectedWordId,
    correct,
    confidence,
    learner_contour: variedContour(detectedTone, accent, id === "phuong-ward" ? "fall" : id === "ma-ghost" ? "flat" : "close"),
    target_contour: pedagogicalContour(intendedTone, accent),
    detected_contour: pedagogicalContour(detectedTone, accent),
    tips_features: { codes: tips, numeric: {} },
    grading_mode: "four_family",
    exact_verified: false,
    family_verified: true,
    alternatives: [{ tone: detectedTone, family: detectedFamily, score: 0.12, confidence }],
    needs_retry: false,
    signal_quality: {
      peak: 0.62,
      rms: 0.18,
      clipping_fraction: 0,
      active_duration_s: 0.72,
      total_duration_s: 1.02,
      voiced_fraction: 0.91,
      longest_voicing_gap_ms: 0,
      island_count: 1,
    },
    tone_family: detectedFamily,
    intended_family: intendedFamily,
    exact_tone_match: detectedTone === intendedTone,
    family_correct: detectedFamily === intendedFamily,
    verification_level: "family",
    tone_alternatives: [{ tone: detectedTone, family: detectedFamily, score: 0.12, probability: confidence }],
    word: intendedWordId,
    intended_word: asAnalysisWord(intendedWord),
    detected_word: asAnalysisWord(detectedWord),
    verdict_copy:
      id === "phuong-ward"
        ? "You meant Phương, the name. You said phường, an urban ward."
        : id === "ma-ghost"
          ? "You meant má, mother. You said ma, a ghost."
          : null,
    target_validated: false,
    semantic_status: correct ? "family_correct" : "wrong_known_word",
    class_confidence: confidence,
    signal_confidence: 0.92,
    meaning_verdict: {
      status: correct ? "family_correct" : "wrong_known_word",
      assertion_level: "family",
      detected_surface: detectedWord.syllable,
      detected_meaning_en: detectedWord.meaning_en,
      detected_word_id: detectedWord.id,
      tone_mark_label:
        detectedTone === "ngang"
          ? "không dấu"
          : detectedTone === "huyen"
            ? "dấu huyền"
            : detectedTone === "sac"
              ? "dấu sắc"
              : detectedTone === "hoi"
                ? "dấu hỏi"
                : detectedTone === "nga"
                  ? "dấu ngã"
                  : "dấu nặng",
    },
    classifier_version: "committed-demo-v2",
    classifier_manifest_hash: "offline-demo-receipt",
  };
}

export function demoCoach(id: "phuong-ward" | "ma-ghost" | "ma-correct"): CoachResult {
  if (id === "phuong-ward") {
    return {
      observation: "Your ending fell toward the falling family instead of staying level.",
      coaching_sentence: "Hold your chin steady and carry Phương straight across without letting the ending sink.",
      next_word: "phuong-ward",
      rationale: "Contrast the level name with phường while that accidental fall is fresh.",
      source: "rules",
    };
  }
  if (id === "ma-ghost") {
    return {
      observation: "Your pitch stayed level instead of rising through the final half of má.",
      coaching_sentence: "Start má lower, then lift your chin and let the vowel climb all the way through.",
      next_word: "ma-mother",
      rationale: "Repeat má because your rising tone flattened into ngang.",
      source: "rules",
    };
  }
  return {
    observation: "Your pitch rose in the same direction as the validated má target.",
    coaching_sentence: "Keep that low start and clean upward sweep; your rise matched the target.",
    next_word: "ma-code",
    rationale: "Move to mã to add a throat catch before a second kind of rise.",
    source: "rules",
  };
}

const ECHO_DEMO_TOKENS: EchoResult["tokens"] = [
  { target: "Tối", heard: "Tối", kind: "match" },
  { target: "nay", heard: "nay", kind: "match" },
  { target: "con", heard: "con", kind: "match" },
  { target: "mời", heard: "mời", kind: "match" },
  { target: "má", heard: "ma", kind: "tone_only", target_word_id: "ma-mother", heard_word_id: "ma-ghost" },
  { target: "đi", heard: "đi", kind: "match" },
  { target: "ăn", heard: "ăn", kind: "match" },
  { target: "cơm", heard: "cơm", kind: "match" },
];

export const ECHO_DEMO: EchoResult = {
  sentence_id: "invite-mom-to-dinner",
  transcript: "Tối nay con mời ma đi ăn cơm.",
  target_text: "Tối nay con mời má đi ăn cơm.",
  tokens: ECHO_DEMO_TOKENS,
  explanation: "You said ma, a ghost, instead of má, mother. You invited a ghost to dinner.",
  literal_explanation: "You said ma, a ghost, instead of má, mother. You invited a ghost to dinner.",
  reveal_id: null,
  source: "committed demo",
  target: "Tối nay con mời má đi ăn cơm.",
  diff: ECHO_DEMO_TOKENS,
};

export function toneById(id: ToneId, tones: Tone[] = TONES): Tone {
  return tones.find((tone) => tone.id === id) ?? TONES[0];
}

export function wordById(id: string | undefined, words: Word[] = FALLBACK_WORDS): Word | undefined {
  return id ? words.find((word) => word.id === id) : undefined;
}
