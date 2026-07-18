import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { RecordControl } from "./RecordControl";

describe("RecordControl", () => {
  it("makes the idle recording action explicit", () => {
    render(<RecordControl state="idle" level={0} elapsedMs={0} onToggle={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Record your tone" }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    expect(screen.getByText("Step 2 · your turn")).toBeTruthy();
    expect(screen.getByText("Tap once, say the word, then pause")).toBeTruthy();
  });

  it("announces a specific busy state and prevents duplicate submissions", () => {
    const { container } = render(
      <RecordControl
        state="processing"
        level={0}
        elapsedMs={900}
        onToggle={vi.fn()}
        processingLabel="Checking your tone marks"
        processingHint="Transcribing the words exactly as heard"
      />,
    );

    const button = screen.getByRole("button", { name: "Checking your tone marks" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(container.querySelector(".record-button__spinner")).not.toBeNull();
    expect(screen.getByText("Transcribing the words exactly as heard")).toBeTruthy();
  });
});
