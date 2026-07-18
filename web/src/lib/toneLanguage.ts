import type { Accent, ToneFamilyId, ToneId, Word } from "../types";

export const TONE_ORDER: ToneId[] = ["ngang", "huyen", "sac", "hoi", "nga", "nang"];

export const TONE_MARK_LABEL: Record<ToneId, string> = {
  ngang: "không dấu",
  huyen: "dấu huyền",
  sac: "dấu sắc",
  hoi: "dấu hỏi",
  nga: "dấu ngã",
  nang: "dấu nặng",
};

export const MA_SURFACES: Record<ToneId, string> = {
  ngang: "ma",
  huyen: "mà",
  sac: "má",
  hoi: "mả",
  nga: "mã",
  nang: "mạ",
};

export const PHUONG_SURFACES: Record<ToneId, string> = {
  ngang: "Phương",
  huyen: "phường",
  sac: "phướng",
  hoi: "phưởng",
  nga: "phưỡng",
  nang: "phượng",
};

export function familyForTone(tone: ToneId, accent: Accent): ToneFamilyId {
  if (tone === "ngang") return "level";
  if (tone === "huyen" || tone === "nang") return "falling";
  if (tone === "hoi" || (tone === "nga" && accent === "south")) return "dipping";
  return "rising";
}

export function toneSurfaceForWord(word: Word, tone: ToneId): string {
  if (word.id.startsWith("ma-")) return MA_SURFACES[tone];
  if (word.id.startsWith("phuong-")) return PHUONG_SURFACES[tone];
  return word.syllable;
}

export function signedSemitones(value: number): string {
  const rounded = Math.abs(value).toFixed(1);
  return `${rounded} semitone${rounded === "1.0" ? "" : "s"}`;
}

export function familyLabel(family: ToneFamilyId): string {
  return family === "level" ? "level" : family === "falling" ? "falling" : family === "rising" ? "rising" : "dipping";
}
