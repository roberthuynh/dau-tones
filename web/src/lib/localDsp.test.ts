import { describe, expect, it } from "vitest";

import { classifyLocalContour } from "./localDsp";

const line = (start: number, end: number) =>
  Array.from({ length: 64 }, (_, index) => start + ((end - start) * index) / 63);

describe("browser-local tone classification", () => {
  it("recognizes level, rising, falling, and short stopped contours", () => {
    expect(classifyLocalContour(line(0.1, 0.2), 0.6, 0, "north")).toBe("ngang");
    expect(classifyLocalContour(line(-1.5, 2), 0.6, 0, "north")).toBe("sac");
    expect(classifyLocalContour(line(1.5, -1.5), 0.6, 0, "north")).toBe("huyen");
    expect(classifyLocalContour(line(1.5, -1.5), 0.25, 0, "north")).toBe("nang");
  });

  it("recognizes dipping contours and northern glottalized rises", () => {
    const dipping = [
      ...line(1, -1.7).slice(0, 34),
      ...line(-1.7, 0.8).slice(0, 30),
    ];
    expect(classifyLocalContour(dipping, 0.6, 0, "north")).toBe("hoi");
    expect(classifyLocalContour(line(-1.5, 2), 0.6, 0.45, "north")).toBe("nga");
  });
});
