import { render } from "@testing-library/react";
import { ToneSyllable } from "./ToneSyllable";

describe("ToneSyllable", () => {
  it("preserves Vietnamese NFC text and isolates its marked grapheme", () => {
    const { container } = render(<ToneSyllable text="Phượng" tone="nang" />);
    expect(container.textContent).toBe("Phượng");
    expect(container.querySelectorAll(".tone-syllable__voiced")).toHaveLength(1);
  });

  it("colors level-tone graphemes without inventing a mark", () => {
    const { container } = render(<ToneSyllable text="Phương" tone="ngang" />);
    expect(container.textContent).toBe("Phương");
    expect(container.querySelector(".tone-text-ngang")).not.toBeNull();
  });
});
