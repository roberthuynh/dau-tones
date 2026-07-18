export type Point = { x: number; y: number };

export function contourPoints(contour: number[], width: number, height: number, insetX = 22, insetY = 22): Point[] {
  if (contour.length === 0) return [];
  const usableWidth = Math.max(1, width - insetX * 2);
  const usableHeight = Math.max(1, height - insetY * 2);
  const pitchFloor = -5.2;
  const pitchCeiling = 5.2;
  return contour.map((pitch, index) => ({
    x: insetX + (index / Math.max(1, contour.length - 1)) * usableWidth,
    y: insetY + ((pitchCeiling - Math.max(pitchFloor, Math.min(pitchCeiling, pitch))) / (pitchCeiling - pitchFloor)) * usableHeight,
  }));
}
export function partialPoints(points: Point[], progress: number): Point[] {
  if (points.length <= 1 || progress >= 1) return points;
  if (progress <= 0) return [];
  const exact = progress * (points.length - 1);
  const endIndex = Math.floor(exact);
  const fraction = exact - endIndex;
  const result = points.slice(0, endIndex + 1);
  const current = points[endIndex];
  const next = points[Math.min(endIndex + 1, points.length - 1)];
  if (fraction > 0 && next) {
    result.push({
      x: current.x + (next.x - current.x) * fraction,
      y: current.y + (next.y - current.y) * fraction,
    });
  }
  return result;
}

export function drawCatmullRom(context: CanvasRenderingContext2D, points: Point[]): void {
  if (points.length === 0) return;
  context.beginPath();
  context.moveTo(points[0].x, points[0].y);
  if (points.length === 1) return;
  if (points.length === 2) {
    context.lineTo(points[1].x, points[1].y);
    return;
  }

  for (let index = 0; index < points.length - 1; index += 1) {
    const p0 = points[Math.max(0, index - 1)];
    const p1 = points[index];
    const p2 = points[index + 1];
    const p3 = points[Math.min(points.length - 1, index + 2)];
    context.bezierCurveTo(
      p1.x + (p2.x - p0.x) / 6,
      p1.y + (p2.y - p0.y) / 6,
      p2.x - (p3.x - p1.x) / 6,
      p2.y - (p3.y - p1.y) / 6,
      p2.x,
      p2.y,
    );
  }
}

export function contourAt(contour: number[], progress: number): number {
  if (contour.length === 0) return 0;
  const exact = Math.max(0, Math.min(1, progress)) * (contour.length - 1);
  const lower = Math.floor(exact);
  const upper = Math.min(contour.length - 1, lower + 1);
  const fraction = exact - lower;
  return contour[lower] + (contour[upper] - contour[lower]) * fraction;
}

export function easeOutCubic(value: number): number {
  return 1 - (1 - value) ** 3;
}
