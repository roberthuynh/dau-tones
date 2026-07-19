import { useEffect, useRef } from "react";
import { MICROPHONE_PRIVACY_VERSION, type MicrophoneIntent } from "../hooks/useMicrophonePrivacy";

type MicrophonePrivacyDialogProps = {
  open: boolean;
  intent: MicrophoneIntent | null;
  liveTranscription: boolean;
  onAcknowledge: () => void;
  onClose: () => void;
};

export function MicrophonePrivacyDialog({
  open,
  intent,
  liveTranscription,
  onAcknowledge,
  onClose,
}: MicrophonePrivacyDialogProps) {
  const actionButtonRef = useRef<HTMLButtonElement>(null);
  const firstRequest = open && intent !== null;
  const showToneShapes = intent === null || intent === "tone_shapes";
  const showDialogue = intent === null || intent === "dialogue";

  useEffect(() => {
    if (!open) return;
    actionButtonRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  const contextLabel = intent === "dialogue" ? "Dialogue Practice" : "Tone Shapes";

  return (
    <div className="modal-backdrop privacy-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section className="privacy-dialog" role="dialog" aria-modal="true" aria-labelledby="microphone-privacy-title">
        <button type="button" className="privacy-dialog__close" onClick={onClose} aria-label="Close microphone privacy notice">×</button>
        <p className="eyebrow">Microphone privacy</p>
        <h2 id="microphone-privacy-title">Your voice stays under your control.</h2>
        {firstRequest ? <p className="privacy-dialog__context">Before {contextLabel} opens your microphone, here is exactly where your recording goes.</p> : null}
        <div className="privacy-dialog__facts">
          {showToneShapes ? <article>
            <span>01</span>
            <div><strong>Tone Shapes stays on this device</strong><p>Pitch extraction and grading run in your browser. The one-word recording is not uploaded.</p></div>
          </article> : null}
          {showDialogue ? <article>
            <span>02</span>
            <div>
              <strong>{liveTranscription ? "Dialogue transcription is on" : "Dialogue stays local without a key"}</strong>
              {liveTranscription ? (
                <p>Your take is sent through Dấu’s server to <code>gpt-4o-transcribe</code>. Dấu retains neither the audio nor the transcript. Browser replay lasts only until you replace the take or leave the page.</p>
              ) : (
                <p>No OpenAI key is active, so your Dialogue recording is not uploaded. Browser replay lasts only until you replace the take or leave the page.</p>
              )}
            </div>
          </article> : null}
          <article>
            <span>03</span>
            <div><strong>The microphone stops after every take</strong><p>Dấu requests browser permission only after you continue, uses the microphone while the record control is live, then stops its audio track.</p></div>
          </article>
        </div>
        <details className="privacy-dialog__learn-more">
          <summary>Learn more about OpenAI API data handling</summary>
          <div>
            <p>OpenAI API data is not used to train models by default.</p>
            <p>Transcription has no application-state or abuse-monitoring retention. Responses and image generation may retain abuse-monitoring data for up to 30 days.</p>
            <p>Dấu sets <code>store=false</code> on every Responses API call. Image generation has no application-state storage.</p>
          </div>
        </details>
        <div className="privacy-dialog__actions">
          {firstRequest ? (
            <button ref={actionButtonRef} type="button" className="button button--primary" onClick={onAcknowledge}>I understand · open microphone</button>
          ) : (
            <button ref={actionButtonRef} type="button" className="button button--primary" onClick={onClose}>Done</button>
          )}
          <small>Notice {MICROPHONE_PRIVACY_VERSION}</small>
        </div>
      </section>
    </div>
  );
}
