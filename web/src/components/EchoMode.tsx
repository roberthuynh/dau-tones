import { useCallback, useEffect, useMemo, useState } from "react";
import { ECHO_DEMO, pedagogicalContour, toneById, wordById } from "../fallbackData";
import { useAudioPlayback } from "../hooks/useAudioPlayback";
import { useRecorder } from "../hooks/useRecorder";
import { getEchoSpeech, getOrCreateReveal, transcribeEcho, transcribeEchoDemo } from "../lib/api";
import type { Accent, EchoDiffToken, EchoResult, EchoSentence, ToneId, Word, WordsPayload } from "../types";
import { CoDau } from "./CoDau";
import { ArrowIcon, PlayIcon, SparkIcon, VolumeIcon } from "./Icons";
import { MeaningArt } from "./MeaningArt";
import { RecordControl } from "./RecordControl";
import { ToneSyllable } from "./ToneSyllable";

type EchoModeProps = {
  accent: Accent;
  sentences: EchoSentence[];
  payload: WordsPayload;
  liveTranscription: boolean;
};

function responseTokens(result: EchoResult): EchoDiffToken[] {
  return result.tokens;
}

function sentenceTone(sentence: EchoSentence): ToneId {
  if (sentence.id === "me-toi-ten-la-phuong") return "ngang";
  if (sentence.id === "invite-mom-to-dinner") return "sac";
  if (sentence.id.includes("pho") || sentence.id.includes("khoe")) return "hoi";
  return "huyen";
}

function TokenDiff({ token, words }: { token: EchoDiffToken; words: Word[] }) {
  const changed = token.kind !== "match";
  const targetWord = wordById(token.target_word_id ?? undefined, words);
  const heardWord = wordById(token.heard_word_id ?? undefined, words);
  return (
    <span className={`echo-token ${changed ? "echo-token--changed" : ""} echo-token--${token.kind}`}>
      <span className="echo-token__heard">{token.heard ?? "∅"}</span>
      {changed ? (
        <span className="echo-token__note">
          {targetWord && heardWord ? `${heardWord.meaning_en}, not ${targetWord.meaning_en}` : token.target ? `target: ${token.target}` : token.kind}
        </span>
      ) : null}
    </span>
  );
}

export function EchoMode({ accent, sentences, payload, liveTranscription }: EchoModeProps) {
  const [selectedId, setSelectedId] = useState(() => sentences.find((sentence) => sentence.id === "me-toi-ten-la-phuong")?.id ?? sentences[0]?.id);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const [result, setResult] = useState<EchoResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generatedRevealArt, setGeneratedRevealArt] = useState<string | null>(null);
  const sentence = sentences.find((item) => item.id === selectedId) ?? sentences[0];
  const toneId = sentenceTone(sentence);
  const tone = toneById(toneId, payload.tones);
  const targetContour = pedagogicalContour(toneId, accent);
  const correctAudio = useAudioPlayback();
  const tokens = useMemo(() => (result ? responseTokens(result) : []), [result]);
  const changedToken = tokens.find((token) => token.kind !== "match");
  const intendedWord = wordById(changedToken?.target_word_id ?? undefined, payload.words);
  const heardWord = wordById(changedToken?.heard_word_id ?? undefined, payload.words);

  const selectSentence = (sentenceId: string) => {
    setSelectedId(sentenceId);
    setResult(null);
    setError(null);
    setGeneratedRevealArt(null);
  };

  useEffect(() => {
    const revealId = result?.reveal_id;
    const revealExplanation = result?.literal_explanation;
    if (!revealId || !revealExplanation) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    const generate = async () => {
      try {
        objectUrl = await getOrCreateReveal(revealId, revealExplanation);
        if (!cancelled) setGeneratedRevealArt(objectUrl);
      } catch {
        // The text diff is the full fallback when live art fails.
      }
    };
    void generate();
    return () => {
      cancelled = true;
      if (objectUrl?.startsWith("blob:")) URL.revokeObjectURL(objectUrl);
    };
  }, [result]);

  useEffect(() => () => {
    if (recordingUrl) URL.revokeObjectURL(recordingUrl);
  }, [recordingUrl]);

  const processRecording = useCallback(
    async (blob: Blob) => {
      setRecordingUrl(URL.createObjectURL(blob));
      setResult(null);
      setGeneratedRevealArt(null);
      setError(null);
      if (!liveTranscription) {
        setError("Live sentence transcription needs an OpenAI key. Replay your recording beside Cô Linh, or run the committed wrong-tone demo.");
        return;
      }
      try {
        setResult(await transcribeEcho(blob, sentence.id, accent));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Dấu could not transcribe that sentence. Your recording is still ready to replay.");
      }
    },
    [accent, liveTranscription, sentence.id],
  );

  const recorder = useRecorder({ onRecording: processRecording, hardStopMs: 12_000, silenceMs: 1_100, minimumMs: 500 });

  const playCorrect = async () => {
    setError(null);
    try {
      const source = await getEchoSpeech(sentence.id, accent);
      await correctAudio.play(source);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Correct playback is unavailable right now.");
    }
  };

  const runDemo = async () => {
    const demoSentence = sentences.find((item) => item.id === "invite-mom-to-dinner");
    if (demoSentence) selectSentence(demoSentence.id);
    setGeneratedRevealArt(null);
    setError(null);
    try {
      setResult(await transcribeEchoDemo("invite-mom-to-dinner", "invite-mom-said-ghost"));
    } catch {
      setResult(ECHO_DEMO);
    }
  };

  const explanation = result?.explanation;
  const revealArt = generatedRevealArt;
  const progressLabel = useMemo(() => {
    if (!result) return "Speak it, then see where the meaning moved.";
    const differences = tokens.filter((token) => token.kind !== "match").length;
    return differences === 0 ? "Every word landed." : `${differences} ${differences === 1 ? "word changed" : "words changed"}.`;
  }, [result, tokens]);

  return (
    <main className="echo-mode page-enter">
      <header className="echo-hero">
        <div>
          <p className="eyebrow">Echo · sentence mode</p>
          <h1>Tones carry the stakes.</h1>
          <p>Say the whole thought. Dấu finds the tiny tone change that rewrites it, then Cô Linh says it back for shadowing.</p>
        </div>
        <div className="echo-hero__orb" aria-hidden="true"><span>ý</span><span>nghĩa</span></div>
      </header>

      <div className="echo-layout">
        <nav className="sentence-rail" aria-label="Echo sentences">
          <div className="sentence-rail__heading"><span>8 useful sentences</span><small>{accent === "north" ? "Hà Nội" : "Sài Gòn"} reference</small></div>
          {sentences.map((item, index) => (
            <button type="button" key={item.id} className={item.id === sentence.id ? "active" : ""} onClick={() => selectSentence(item.id)} aria-current={item.id === sentence.id ? "true" : undefined}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <span><strong lang="vi">{item.text}</strong><small>{item.gloss_en}</small></span>
            </button>
          ))}
        </nav>

        <section className="echo-stage" style={{ "--active-tone": tone.color } as React.CSSProperties}>
          <div className="echo-sentence-target">
            <span className="eyebrow">Say this naturally</span>
            <h2 lang="vi">{sentence.text}</h2>
            <p>{sentence.gloss_en}</p>
          </div>

          <div className="echo-practice-row">
            <CoDau compact contour={targetContour} tone={toneId} word={sentence.text} progress={correctAudio.progress} playing={correctAudio.playing} />
            <div className="echo-record-zone">
              <RecordControl
                state={recorder.state}
                level={recorder.level}
                elapsedMs={recorder.elapsedMs}
                onToggle={recorder.toggle}
                label="Record the sentence"
                idleHint="Tap once, speak naturally, then pause"
                processingLabel="Checking your tone marks"
                processingHint="Transcribing the words exactly as heard"
              />
              <div className="echo-playback-pair">
                <button type="button" disabled={!recordingUrl} onClick={() => recordingUrl && void new Audio(recordingUrl).play()}>
                  <PlayIcon /><span><strong>Your take</strong><small>{recordingUrl ? "ready to replay" : "record first"}</small></span>
                </button>
                <button type="button" onClick={() => void playCorrect()}>
                  {correctAudio.playing ? <VolumeIcon /> : <PlayIcon />}<span><strong>Cô Linh's take</strong><small>correct shadowing</small></span>
                </button>
              </div>
            </div>
          </div>

          {recorder.error || error || correctAudio.error ? (
            <div className="inline-error" role="alert"><span>{recorder.error || error || correctAudio.error}</span><button type="button" onClick={() => { recorder.clearError(); correctAudio.clearError(); setError(null); }}>Dismiss</button></div>
          ) : null}

          <div className="echo-demo-callout">
            <span><SparkIcon /> No key or no Vietnamese?</span>
            <p>Run the committed dinner demo to see a single accent mark invite the wrong guest.</p>
            <button type="button" onClick={() => void runDemo()}>Try “a ghost at dinner” <ArrowIcon /></button>
          </div>
        </section>

        <aside className={`echo-reveal ${result ? "echo-reveal--shown" : ""}`} aria-live="polite">
          {!result ? (
            <div className="echo-empty">
              <span className="echo-empty__mark">´</span>
              <h2>One mark can change the guest.</h2>
              <p>{progressLabel}</p>
            </div>
          ) : (
            <>
              <div className="echo-transcript">
                <p className="eyebrow">What Dấu heard</p>
                <div lang="vi">{tokens.length ? tokens.map((token, index) => <TokenDiff key={`${token.heard}-${index}`} token={token} words={payload.words} />) : result.transcript}</div>
              </div>
              {explanation ? (
                <div className="literal-reveal">
                  <span className="literal-reveal__icon"><SparkIcon /></span>
                  <p>{explanation}</p>
                </div>
              ) : null}
              {intendedWord && heardWord ? (
                <div className="echo-meaning-pair">
                  <div><MeaningArt word={intendedWord} eager /><span>meant</span><strong><ToneSyllable text={intendedWord.syllable} tone={intendedWord.tone} /></strong><small>{intendedWord.meaning_en}</small></div>
                  <ArrowIcon />
                  <div><MeaningArt word={heardWord} eager /><span>heard</span><strong><ToneSyllable text={heardWord.syllable} tone={heardWord.tone} /></strong><small>{heardWord.meaning_en}</small></div>
                </div>
              ) : null}
              {revealArt ? <div className="wrong-sentence-art"><img src={revealArt} alt="Literal illustration of the accidentally spoken sentence" /></div> : null}
              <button type="button" className="button button--primary echo-shadow-button" onClick={() => void playCorrect()}>
                <VolumeIcon /> Hear it correctly, then shadow
              </button>
            </>
          )}
        </aside>
      </div>
    </main>
  );
}
