import { wordById } from "../../fallbackData";
import { toneOfVietnameseSurface, type EchoCourseResult } from "../../lib/echoCourse";
import { useState } from "react";
import type { EchoDiffToken, ToneId, Word } from "../../types";
import { ArrowIcon, PlayIcon, SparkIcon, VolumeIcon } from "../Icons";
import { MeaningArt } from "../MeaningArt";
import { ToneSyllable } from "../ToneSyllable";

const TONE_MARKS: Record<ToneId, string> = {
  ngang: "không dấu",
  huyen: "dấu huyền",
  sac: "dấu sắc",
  hoi: "dấu hỏi",
  nga: "dấu ngã",
  nang: "dấu nặng",
};

type EchoResultPanelProps = {
  result: EchoCourseResult;
  words: Word[];
  recordingUrl: string | null;
  revealArtUrl: string | null;
  onPlayLearner: () => void;
  onPlayCorrect: () => void;
  onPracticeWord: (wordId: string) => void;
  onRetry: () => void;
  onContinue: () => void;
  continuingLabel: string;
};

function changedTokens(result: EchoCourseResult): EchoDiffToken[] {
  return (result.tokens.length ? result.tokens : result.diff).filter((token) => token.kind !== "match");
}

function TranscriptToken({ token }: { token: EchoDiffToken }) {
  const changed = token.kind !== "match";
  return (
    <span className={`echo-course__token ${changed ? "is-changed" : ""} echo-course__token--${token.kind}`}>
      <span>{token.heard ?? "∅"}</span>
      {changed && token.target ? <small>{token.target}</small> : null}
    </span>
  );
}

function RevealArt({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  return failed ? null : <img className="echo-course__mistake-art" src={src} alt="Literal illustration of how the changed tone altered the scene" onError={() => setFailed(true)} />;
}

function DifferenceCard({ token, words, onPracticeWord }: { token: EchoDiffToken; words: Word[]; onPracticeWord: (wordId: string) => void }) {
  const intended = wordById(token.target_word_id ?? undefined, words);
  const heard = wordById(token.heard_word_id ?? undefined, words);
  const practiceId = intended?.id ?? heard?.id;
  const heardLabel = token.heard ?? "a missing word";
  const inferredHeardTone = token.heard ? toneOfVietnameseSurface(token.heard) : null;
  return (
    <article className="echo-course__difference">
      <div className="echo-course__difference-head">
        <span>{token.kind === "tone_only" ? "Tone mark changed" : token.kind === "missing" ? "Word missing" : token.kind === "extra" ? "Extra word" : "Word changed"}</span>
        <strong lang="vi">{token.target ?? "∅"} <ArrowIcon /> {heardLabel}</strong>
      </div>
      {intended || heard ? (
        <div className="echo-course__meaning-compare">
          {intended ? (
            <div>
              <MeaningArt word={intended} eager />
              <span>you meant</span>
              <strong lang="vi"><ToneSyllable text={intended.syllable} tone={intended.tone} /></strong>
              <small>{TONE_MARKS[intended.tone]} · {intended.meaning_en}</small>
            </div>
          ) : null}
          {heard ? (
            <div className="is-heard">
              <MeaningArt word={heard} eager />
              <span>Dấu heard</span>
              <strong lang="vi"><ToneSyllable text={heard.syllable} tone={heard.tone} /></strong>
              <small>{TONE_MARKS[heard.tone]} · {heard.meaning_en}</small>
            </div>
          ) : (
            <div className="is-unknown">
              <span>Dấu heard</span>
              <strong lang="vi">{heardLabel}</strong>
              <small>{inferredHeardTone ? `${TONE_MARKS[inferredHeardTone]} · ` : ""}No curated meaning for this form in the lesson.</small>
            </div>
          )}
        </div>
      ) : <p>{token.meaning_explanation ?? `Dấu heard “${heardLabel}” where the target had “${token.target ?? "nothing"}”.`}</p>}
      {practiceId ? <button type="button" onClick={() => onPracticeWord(practiceId)}>Practice this word in Tone Shapes <ArrowIcon /></button> : null}
    </article>
  );
}

export function EchoResultPanel({
  result,
  words,
  recordingUrl,
  revealArtUrl,
  onPlayLearner,
  onPlayCorrect,
  onPracticeWord,
  onRetry,
  onContinue,
  continuingLabel,
}: EchoResultPanelProps) {
  const differences = changedTokens(result);
  const correct = differences.length === 0;
  return (
    <section className={`echo-course__feedback ${correct ? "is-correct" : "is-changed"}`} aria-live="polite">
      <div className="echo-course__feedback-title">
        <span className="echo-course__feedback-icon">{correct ? "✓" : "!"}</span>
        <div>
          <small>{correct ? "Sentence matched" : `${differences.length} ${differences.length === 1 ? "word needs" : "words need"} attention`}</small>
          <h3>{correct ? "Every tone mark landed." : "Here is exactly what changed."}</h3>
        </div>
      </div>

      <div className="echo-course__heard">
        <span>What Dấu heard</span>
        <p lang="vi">{result.tokens.length ? result.tokens.map((token, index) => <TranscriptToken key={`${token.heard ?? "missing"}-${index}`} token={token} />) : result.transcript}</p>
      </div>

      {!correct ? <div className="echo-course__differences">{differences.map((token, index) => <DifferenceCard key={`${token.target}-${token.heard}-${index}`} token={token} words={words} onPracticeWord={onPracticeWord} />)}</div> : null}

      {result.literal_explanation || result.explanation ? (
        <div className="echo-course__literal"><SparkIcon /><p>{result.literal_explanation || result.explanation}</p></div>
      ) : null}

      {revealArtUrl ? <RevealArt key={revealArtUrl} src={revealArtUrl} /> : null}

      <div className="echo-course__replay-grid">
        <button type="button" disabled={!recordingUrl} onClick={onPlayLearner}><PlayIcon /><span><strong>Your take</strong><small>{recordingUrl ? "replay what you said" : "recording unavailable"}</small></span></button>
        <button type="button" onClick={onPlayCorrect}><VolumeIcon /><span><strong>Correct take</strong><small>shadow Thầy Minh</small></span></button>
      </div>
      <div className="echo-course__result-actions">
        <button type="button" className="echo-course__retry-line" onClick={onRetry}><span aria-hidden="true">↺</span> Practice again</button>
        <button type="button" className="echo-course__continue" onClick={onContinue}>{continuingLabel} <ArrowIcon /></button>
      </div>
    </section>
  );
}
