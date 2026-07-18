export type VowelShape = "open" | "rounded" | "spread";

export function vowelShapeForWord(word: string): VowelShape {
  const firstVowel = Array.from(word.normalize("NFD").toLocaleLowerCase("vi")).find((character) => /[aeiouy]/.test(character));
  if (firstVowel === "o" || firstVowel === "u") return "rounded";
  if (firstVowel === "e" || firstVowel === "i" || firstVowel === "y") return "spread";
  return "open";
}
