import canonicalCourse from "../data/echo-scenes.generated.json";
import type { Accent, EchoDiffToken, EchoResult, ToneId, Word } from "../types";

export type EchoRole = "minh" | "learner";

export type EchoFocus = {
  token_index: number;
  token: string;
  tone: ToneId;
  word_id?: string;
  meaning_en?: string;
};

export type EchoTurn = {
  id: string;
  role: EchoRole;
  text: string;
  gloss_en: string;
  focus: EchoFocus;
  focuses: EchoFocus[];
  audio_urls: Record<Accent, string>;
};

export type EchoFixture = {
  id: string;
  turn_id: string;
  label: string;
  heard_text: string;
  audio_url: string;
  explanation: string;
  tokens: EchoDiffToken[];
  reveal_art_url?: string;
  practice_word_ids: string[];
};

export type EchoScene = {
  id: string;
  number: number;
  title: string;
  subtitle: string;
  location: string;
  art_url: string;
  art_alt: string;
  title_vi: string;
  description: string;
  turns: EchoTurn[];
  fixture: EchoFixture;
};

export type EchoLocation = {
  sceneId: string;
  turnId: string;
  focus: string | null;
};

export type EchoCourseResult = EchoResult & {
  scene_id?: string;
  turn_id?: string;
  next_turn_id?: string | null;
  practice_word_ids?: string[];
  reveal_art_url?: string | null;
  semantic_status?: string;
};

type CanonicalFocus = {
  token_index: number;
  token: string;
  tone: string;
  word_id: string | null;
  meaning_en: string | null;
};

type CanonicalStake = {
  target_token: string;
  heard_token: string;
  intended_word_id: string;
  heard_word_id: string;
  explanation: string;
};

type CanonicalTurn = {
  id: string;
  speaker: EchoRole;
  text: string;
  gloss_en: string;
  focuses: CanonicalFocus[];
  literal_stakes?: CanonicalStake[];
  shadow_audio: Record<Accent, string>;
};

type CanonicalScene = {
  id: string;
  order: number;
  title: string;
  title_vi: string;
  description: string;
  art_url: string;
  offline_demo: {
    id: string;
    turn_id: string;
    committed_transcript: string;
    recording_path: string;
    mistake_art_url: string | null;
  };
  turns: CanonicalTurn[];
};

type CanonicalCourse = {
  schema_version: number;
  locale: string;
  scenes: CanonicalScene[];
};

type FixturePresentation = {
  label: string;
  explanation: string;
  heard_word_id?: string;
};

type ScenePresentation = {
  subtitle: string;
  location: string;
  art_alt: string;
  fixture: FixturePresentation;
};

const SCENE_PRESENTATION: Record<string, ScenePresentation> = {
  "meet-family": {
    subtitle: "Names that differ by one mark",
    location: "At the family home",
    art_alt: "Minh arriving at a warm Vietnamese family home as the family welcomes him",
    fixture: {
      label: "Try the ghost-at-dinner mistake",
      explanation: "You said ma (ghost) instead of má (mother). That turns a family dinner into an invitation for a ghost.",
      heard_word_id: "ma-ghost",
    },
  },
  "family-dinner": {
    subtitle: "Bring the right thing",
    location: "Around the dinner table",
    art_alt: "A Vietnamese family and Minh gathered around a warm dinner table",
    fixture: {
      label: "Try the rice-seedling door code",
      explanation: "You said mạ (rice seedling) instead of mã (code).",
      heard_word_id: "ma-seedling",
    },
  },
  "pho-shop": {
    subtitle: "Order a full breakfast",
    location: "A neighborhood noodle shop",
    art_alt: "Minh and a learner ordering breakfast inside a welcoming Vietnamese phở shop",
    fixture: {
      label: "Try a changed phở tone",
      explanation: "Dấu heard không dấu on “phở.” That form has no curated meaning in this lesson.",
    },
  },
  "around-ward": {
    subtitle: "Ask, turn, and find your way",
    location: "Walking through the neighborhood",
    art_alt: "Minh and a learner walking through a Vietnamese neighborhood near fields and a ward office",
    fixture: {
      label: "Try ghost instead of grave",
      explanation: "You said ma (ghost) instead of mả (grave).",
      heard_word_id: "ma-ghost",
    },
  },
};

const TONE_IDS = new Set<ToneId>(["ngang", "huyen", "sac", "hoi", "nga", "nang"]);

function toneId(value: string): ToneId {
  if (!TONE_IDS.has(value as ToneId)) throw new Error(`Unknown Echo tone: ${value}`);
  return value as ToneId;
}

function publicAudioPath(targetPath: string): string {
  if (!targetPath.startsWith("targets/")) throw new Error(`Invalid committed audio path: ${targetPath}`);
  return `/audio/${targetPath.slice("targets/".length)}`;
}

function focusFromCanonical(source: CanonicalFocus): EchoFocus {
  return {
    token_index: source.token_index,
    token: source.token,
    tone: toneId(source.tone),
    ...(source.word_id ? { word_id: source.word_id } : {}),
    ...(source.meaning_en ? { meaning_en: source.meaning_en } : {}),
  };
}

function turnFromCanonical(source: CanonicalTurn): EchoTurn {
  const focuses = source.focuses.map(focusFromCanonical);
  const focus = focuses[0];
  if (!focus) throw new Error(`Echo turn ${source.id} has no contour focus.`);
  return {
    id: source.id,
    role: source.speaker,
    text: source.text,
    gloss_en: source.gloss_en,
    focus,
    focuses,
    audio_urls: {
      north: publicAudioPath(source.shadow_audio.north),
      south: publicAudioPath(source.shadow_audio.south),
    },
  };
}

function normalizeToken(token: string): string {
  return token.normalize("NFC").toLocaleLowerCase("vi-VN").replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
}

function fixtureTokens(
  targetTurn: CanonicalTurn,
  heardText: string,
  presentation: FixturePresentation,
): EchoDiffToken[] {
  const target = targetTurn.text.split(/\s+/);
  const heard = heardText.split(/\s+/);
  return target.map((targetToken, index) => {
    const heardToken = heard[index] ?? null;
    const normalizedTarget = normalizeToken(targetToken);
    const normalizedHeard = normalizeToken(heardToken ?? "");
    const isChanged = normalizedTarget !== normalizedHeard;
    const stake = targetTurn.literal_stakes?.find(
      (item) => normalizeToken(item.target_token) === normalizedTarget && normalizeToken(item.heard_token) === normalizedHeard,
    );
    const focus = targetTurn.focuses.find((item) => normalizeToken(item.token) === normalizedTarget);
    return {
      target: targetToken,
      heard: heardToken,
      kind: isChanged ? "tone_only" : "match",
      target_word_id: isChanged ? stake?.intended_word_id ?? focus?.word_id ?? null : null,
      heard_word_id: isChanged ? stake?.heard_word_id ?? presentation.heard_word_id ?? null : null,
      meaning_explanation: isChanged ? stake?.explanation ?? presentation.explanation : null,
    };
  });
}

function sceneFromCanonical(source: CanonicalScene): EchoScene {
  const presentation = SCENE_PRESENTATION[source.id];
  if (!presentation) throw new Error(`Missing browser presentation for Echo scene ${source.id}.`);
  const targetTurn = source.turns.find((item) => item.id === source.offline_demo.turn_id);
  if (!targetTurn) throw new Error(`Echo fixture ${source.offline_demo.id} has no target turn.`);
  const tokens = fixtureTokens(
    targetTurn,
    source.offline_demo.committed_transcript,
    presentation.fixture,
  );
  const practiceWordIds = Array.from(
    new Set(
      tokens.flatMap((item) => [item.target_word_id, item.heard_word_id]).filter((id): id is string => Boolean(id)),
    ),
  );
  return {
    id: source.id,
    number: source.order,
    title: source.title,
    title_vi: source.title_vi,
    description: source.description,
    subtitle: presentation.subtitle,
    location: presentation.location,
    art_url: source.art_url,
    art_alt: presentation.art_alt,
    turns: source.turns.map(turnFromCanonical),
    fixture: {
      id: source.offline_demo.id,
      turn_id: source.offline_demo.turn_id,
      label: presentation.fixture.label,
      heard_text: source.offline_demo.committed_transcript,
      audio_url: publicAudioPath(source.offline_demo.recording_path),
      explanation: presentation.fixture.explanation,
      tokens,
      ...(source.offline_demo.mistake_art_url
        ? { reveal_art_url: source.offline_demo.mistake_art_url }
        : {}),
      practice_word_ids: practiceWordIds,
    },
  };
}

export const ECHO_COURSE_SOURCE = canonicalCourse as CanonicalCourse;
export const ECHO_SCENES: EchoScene[] = ECHO_COURSE_SOURCE.scenes.map(sceneFromCanonical);

export function learnerTurns(scene: EchoScene): EchoTurn[] {
  return scene.turns.filter((item) => item.role === "learner");
}

export function toneOfVietnameseSurface(surface: string): ToneId {
  const marks = new Set(surface.normalize("NFD"));
  if (marks.has("\u0323")) return "nang";
  if (marks.has("\u0303")) return "nga";
  if (marks.has("\u0309")) return "hoi";
  if (marks.has("\u0301")) return "sac";
  if (marks.has("\u0300")) return "huyen";
  return "ngang";
}

export function isOwnedEchoObjectUrl(url: string | null): boolean {
  return Boolean(url?.startsWith("blob:"));
}

function focusMatches(itemFocus: EchoFocus, requestedFocus: string): boolean {
  return itemFocus.word_id === requestedFocus
    || itemFocus.token.toLocaleLowerCase("vi-VN") === requestedFocus.toLocaleLowerCase("vi-VN");
}

export function focusForTurn(turn: EchoTurn, requestedFocus?: string | null): EchoFocus {
  if (!requestedFocus) return turn.focus;
  return turn.focuses.find((itemFocus) => focusMatches(itemFocus, requestedFocus)) ?? turn.focus;
}

export function targetContourForFocus(
  focus: EchoFocus,
  accent: Accent,
  words: Word[],
): number[] | null {
  if (!focus.word_id) return null;
  const contour = words.find((word) => word.id === focus.word_id)?.targets[accent]?.contour;
  return contour?.length ? contour : null;
}

export function nextLearnerTurn(scene: EchoScene, afterTurnId?: string): EchoTurn | null {
  const startIndex = afterTurnId ? scene.turns.findIndex((item) => item.id === afterTurnId) + 1 : 0;
  return scene.turns.slice(Math.max(0, startIndex)).find((item) => item.role === "learner") ?? null;
}

export function precedingPartnerTurn(scene: EchoScene, learnerTurnId: string): EchoTurn | null {
  const learnerIndex = scene.turns.findIndex((item) => item.id === learnerTurnId);
  if (learnerIndex <= 0) return null;
  const candidate = scene.turns[learnerIndex - 1];
  return candidate.role === "minh" ? candidate : null;
}

export function findLearnerTurnForFocus(scenes: EchoScene[], focus: string): { scene: EchoScene; turn: EchoTurn } | null {
  for (const scene of scenes) {
    const turn = scene.turns.find((item) => item.role === "learner" && item.focuses.some(
      (itemFocus) => focusMatches(itemFocus, focus),
    ));
    if (turn) return { scene, turn };
  }
  return null;
}

export function readEchoCourseLocation(search: string, scenes: EchoScene[] = ECHO_SCENES): EchoLocation {
  const params = new URLSearchParams(search);
  const requestedScene = params.get("scene");
  const scene = scenes.find((item) => item.id === requestedScene) ?? scenes[0];
  const requestedTurn = params.get("turn");
  const turn = scene.turns.find((item) => item.id === requestedTurn && item.role === "learner") ?? nextLearnerTurn(scene);
  return { sceneId: scene.id, turnId: turn?.id ?? scene.turns[0]?.id ?? "", focus: params.get("focus") };
}

export function writeEchoCourseLocation(sceneId: string, turnId?: string | null, focus?: string | null): string {
  const current = typeof window === "undefined" ? new URLSearchParams() : new URLSearchParams(window.location.search);
  current.set("mode", "dialogue");
  current.set("scene", sceneId);
  if (turnId) current.set("turn", turnId);
  else current.delete("turn");
  if (focus) current.set("focus", focus);
  else current.delete("focus");
  return `?${current.toString()}`;
}

export function fixtureAsResult(scene: EchoScene): EchoCourseResult {
  const fixture = scene.fixture;
  const turnItem = scene.turns.find((item) => item.id === fixture.turn_id) ?? scene.turns[0];
  return {
    scene_id: scene.id,
    turn_id: fixture.turn_id,
    next_turn_id: nextLearnerTurn(scene, fixture.turn_id)?.id ?? null,
    sentence_id: fixture.turn_id,
    transcript: fixture.heard_text,
    target_text: turnItem.text,
    tokens: fixture.tokens,
    explanation: fixture.explanation,
    literal_explanation: fixture.explanation,
    reveal_id: null,
    source: "fixture",
    target: turnItem.text,
    diff: fixture.tokens,
    reveal_art_url: fixture.reveal_art_url ?? null,
    practice_word_ids: fixture.practice_word_ids,
  };
}

const COMMITTED_MISTAKE_ART: Record<string, string> = {
  "ma-mother:ma-ghost": "/art/scenes/mistake-ghost-dinner.webp",
  "phuong-name:phuong-ward": "/art/scenes/mistake-ward-mother.webp",
  "ma-code:ma-seedling": "/art/scenes/mistake-seedling-code.webp",
};

export function committedMistakeArt(result: EchoCourseResult): string | null {
  for (const token of result.tokens.length ? result.tokens : result.diff) {
    if (!token.target_word_id || !token.heard_word_id) continue;
    const art = COMMITTED_MISTAKE_ART[`${token.target_word_id}:${token.heard_word_id}`];
    if (art) return art;
  }
  return null;
}
