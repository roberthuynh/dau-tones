import { useEffect, useMemo, useRef, useState } from "react";
import type { SessionToneStat, Tone } from "../types";
import { CloseIcon, DownloadIcon } from "./Icons";

type SummaryModalProps = {
  open: boolean;
  onClose: () => void;
  stats: Record<string, SessionToneStat>;
  streak: number;
  coachLine: string;
  tones: Tone[];
};

function roundedRect(context: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
  context.fill();
}

function wrapText(context: CanvasRenderingContext2D, text: string, maxWidth: number): string[] {
  const words = text.split(/\s+/);
  const lines: string[] = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (context.measureText(next).width > maxWidth && line) {
      lines.push(line);
      line = word;
    } else line = next;
  }
  if (line) lines.push(line);
  return lines;
}

export function SummaryModal({ open, onClose, stats, streak, coachLine, tones }: SummaryModalProps) {
  const [exporting, setExporting] = useState(false);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const totals = useMemo(() => Object.values(stats).reduce((sum, entry) => ({ attempts: sum.attempts + entry.attempts, correct: sum.correct + entry.correct }), { attempts: 0, correct: 0 }), [stats]);

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    closeButtonRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previousFocus?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;

  const exportCard = async () => {
    setExporting(true);
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1200;
      canvas.height = 630;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.fillStyle = "#0e0d0c";
      context.fillRect(0, 0, canvas.width, canvas.height);
      const glow = context.createRadialGradient(930, 110, 0, 930, 110, 480);
      glow.addColorStop(0, "rgba(255,107,94,.19)");
      glow.addColorStop(1, "rgba(255,107,94,0)");
      context.fillStyle = glow;
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = "#f3eadb";
      context.font = "700 44px 'Be Vietnam Pro', sans-serif";
      context.fillText("DẤU · TONE SESSION", 70, 86);
      context.font = "700 142px 'Be Vietnam Pro', sans-serif";
      const accuracy = totals.attempts ? Math.round((totals.correct / totals.attempts) * 100) : 0;
      context.fillText(`${accuracy}%`, 68, 252);
      context.fillStyle = "#a49b8e";
      context.font = "500 25px 'Be Vietnam Pro', sans-serif";
      context.fillText(`${totals.correct} of ${totals.attempts} tones landed · best streak ${streak}`, 76, 295);

      const activeTones = tones.filter((tone) => stats[tone.id]?.attempts);
      activeTones.forEach((tone, index) => {
        const x = 72 + index * 174;
        const value = stats[tone.id];
        const percentage = Math.round((value.correct / value.attempts) * 100);
        context.fillStyle = "#211e1a";
        roundedRect(context, x, 340, 150, 92, 18);
        context.fillStyle = tone.color;
        context.font = "700 24px 'Be Vietnam Pro', sans-serif";
        context.fillText(tone.name_vi, x + 18, 374);
        context.fillStyle = "#f3eadb";
        context.font = "600 28px 'Be Vietnam Pro', sans-serif";
        context.fillText(`${percentage}%`, x + 18, 412);
      });
      context.fillStyle = "#dad0c1";
      context.font = "500 26px 'Be Vietnam Pro', sans-serif";
      const coachLines = wrapText(context, coachLine || "Keep the movement physical: let your chin trace the curve.", 1010).slice(0, 2);
      coachLines.forEach((line, index) => context.fillText(line, 74, 505 + index * 38));
      context.fillStyle = "#ff6b5e";
      context.fillRect(74, 576, 88, 4);
      context.fillStyle = "#8d857a";
      context.font = "500 18px 'Be Vietnam Pro', sans-serif";
      context.fillText("See your tones. Hear what you actually said.", 180, 585);

      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) return;
      const file = new File([blob], "dau-tone-session.png", { type: "image/png" });
      if (navigator.share && navigator.canShare?.({ files: [file] })) {
        await navigator.share({ files: [file], title: "My Dấu tone session" });
      } else {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = file.name;
        link.click();
        window.setTimeout(() => URL.revokeObjectURL(link.href), 500);
      }
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="summary-modal" role="dialog" aria-modal="true" aria-labelledby="summary-title">
        <button ref={closeButtonRef} className="icon-button summary-modal__close" type="button" onClick={onClose} aria-label="Close summary"><CloseIcon /></button>
        <p className="eyebrow">Session complete</p>
        <h2 id="summary-title">Your tones, in focus.</h2>
        <div className="summary-score">
          <strong>{totals.attempts ? Math.round((totals.correct / totals.attempts) * 100) : 0}%</strong>
          <span>{totals.correct} of {totals.attempts} landed</span>
        </div>
        <div className="summary-tones">
          {tones.map((tone) => {
            const entry = stats[tone.id] ?? { attempts: 0, correct: 0 };
            const percentage = entry.attempts ? Math.round((entry.correct / entry.attempts) * 100) : 0;
            return (
              <div key={tone.id} style={{ "--summary-color": tone.color } as React.CSSProperties}>
                <span>{tone.name_vi}</span>
                <strong>{entry.attempts ? `${percentage}%` : "—"}</strong>
              </div>
            );
          })}
        </div>
        <blockquote>{coachLine || "Let your chin trace the contour, then let your voice follow."}</blockquote>
        <button className="button button--primary" type="button" onClick={() => void exportCard()} disabled={exporting}>
          <DownloadIcon /> {exporting ? "Making card…" : "Share summary card"}
        </button>
      </section>
    </div>
  );
}
