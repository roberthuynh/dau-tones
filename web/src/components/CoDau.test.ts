import { vowelShapeForWord } from "../lib/vowel";

describe("Cô Dấu vowel mouth", () => {
  it("keeps Vietnamese tone marks while choosing a stable mouth family", () => {
    expect(vowelShapeForWord("má")).toBe("open");
    expect(vowelShapeForWord("Phương")).toBe("rounded");
    expect(vowelShapeForWord("mẹ")).toBe("spread");
  });
});
