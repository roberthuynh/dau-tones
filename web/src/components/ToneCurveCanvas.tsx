import { useEffect, useRef, useState } from "react";
import { contourPoints, drawCatmullRom, easeOutCubic, partialPoints } from "../lib/curve";
import { useReducedMotion } from "../hooks/useReducedMotion";

type ToneCurveCanvasProps = {
  target: number[];
  learner?: number[] | null;
  ghost?: number[] | null;
  toneColor: string;
  ghostColor?: string;
  revealKey?: string | number;
  correct?: boolean;
  ariaLabel: string;
};

type CanvasSize = { width: number; height: number };

function drawGrid(context: CanvasRenderingContext2D, width: number, height: number) {
  context.save();
  context.strokeStyle = "rgba(237, 228, 211, 0.055)";
  context.lineWidth = 1;
  const columns = 8;
  const rows = 4;
  for (let index = 1; index < columns; index += 1) {
    const x = Math.round((width * index) / columns) + 0.5;
    context.beginPath();
    context.moveTo(x, 16);
    context.lineTo(x, height - 16);
    context.stroke();
  }
  for (let index = 1; index < rows; index += 1) {
    const y = Math.round((height * index) / rows) + 0.5;
    context.beginPath();
    context.moveTo(16, y);
    context.lineTo(width - 16, y);
    context.stroke();
  }
  context.restore();
}

function strokeCurve(
  context: CanvasRenderingContext2D,
  points: ReturnType<typeof contourPoints>,
  color: string,
  width: number,
  dash: number[] = [],
  alpha = 1,
  glow = 0,
) {
  context.save();
  context.globalAlpha = alpha;
  context.strokeStyle = color;
  context.lineWidth = width;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.setLineDash(dash);
  context.shadowColor = color;
  context.shadowBlur = glow;
  drawCatmullRom(context, points);
  context.stroke();
  context.restore();
}

export function ToneCurveCanvas({ target, learner, ghost, toneColor, ghostColor = "#ffffff", revealKey = 0, correct = false, ariaLabel }: ToneCurveCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState<CanvasSize>({ width: 800, height: 360 });
  const reducedMotion = useReducedMotion();

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) return;
    if (typeof ResizeObserver === "undefined") {
      const bounds = wrapper.getBoundingClientRect();
      if (bounds.width > 0 && bounds.height > 0) setSize({ width: Math.round(bounds.width), height: Math.round(bounds.height) });
      return;
    }
    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(280, Math.round(entry.contentRect.width));
      const height = Math.max(230, Math.round(entry.contentRect.height));
      setSize((current) => (current.width === width && current.height === height ? current : { width, height }));
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(size.height * dpr);
    canvas.style.width = `${size.width}px`;
    canvas.style.height = `${size.height}px`;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);

    const started = performance.now();
    const duration = reducedMotion || !learner ? 0 : 600;
    let frame = 0;
    const render = (now: number) => {
      const rawProgress = duration === 0 ? 1 : Math.min(1, (now - started) / duration);
      const progress = easeOutCubic(rawProgress);
      context.clearRect(0, 0, size.width, size.height);
      drawGrid(context, size.width, size.height);

      const targetPoints = contourPoints(target, size.width, size.height, 28, 26);
      strokeCurve(context, targetPoints, "rgba(235, 226, 207, 0.58)", 2, [8, 10]);

      if (ghost?.length) {
        const ghostPoints = contourPoints(ghost, size.width, size.height, 28, 26);
        strokeCurve(context, ghostPoints, ghostColor, 3, [3, 10], 0.32, 4);
      }
      if (learner?.length) {
        const learnerPoints = partialPoints(contourPoints(learner, size.width, size.height, 28, 26), progress);
        strokeCurve(context, learnerPoints, toneColor, correct && rawProgress === 1 ? 5 : 4, [], 0.98, correct && rawProgress === 1 ? 19 : 13);
        if (learnerPoints.length) {
          const last = learnerPoints[learnerPoints.length - 1];
          context.save();
          context.fillStyle = toneColor;
          context.shadowColor = toneColor;
          context.shadowBlur = 18;
          context.beginPath();
          context.arc(last.x, last.y, 3.5, 0, Math.PI * 2);
          context.fill();
          context.restore();
        }
      }
      if (rawProgress < 1) frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, [correct, ghost, ghostColor, learner, reducedMotion, revealKey, size, target, toneColor]);

  return (
    <div ref={wrapperRef} className={`curve-canvas ${correct ? "curve-canvas--correct" : ""}`}>
      <canvas ref={canvasRef} role="img" aria-label={ariaLabel} />
      <span className="curve-label curve-label--target">reference target</span>
      {learner ? <span className="curve-label curve-label--learner">what you said</span> : null}
    </div>
  );
}
