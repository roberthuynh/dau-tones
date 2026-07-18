import { contourAt, contourPoints, partialPoints } from "./curve";

describe("curve helpers", () => {
  it("maps a complete contour into the canvas inset", () => {
    const points = contourPoints([-5.2, 0, 5.2], 200, 100, 20, 10);
    expect(points).toHaveLength(3);
    expect(points[0]).toEqual({ x: 20, y: 90 });
    expect(points[2]).toEqual({ x: 180, y: 10 });
  });

  it("reveals a fractional final point instead of jumping by sample", () => {
    const points = [{ x: 0, y: 10 }, { x: 10, y: 0 }, { x: 20, y: 10 }];
    expect(partialPoints(points, 0.25)).toEqual([{ x: 0, y: 10 }, { x: 5, y: 5 }]);
  });

  it("interpolates avatar pitch between contour samples", () => {
    expect(contourAt([0, 4], 0.25)).toBe(1);
    expect(contourAt([0, 4], 1)).toBe(4);
  });
});
