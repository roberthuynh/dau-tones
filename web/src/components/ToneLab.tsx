import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { demoAnalysis, demoCoach, toneById, wordById } from "../fallbackData";
import { useAudioPlayback } from "../hooks/useAudioPlayback";
import { useRecorder } from "../hooks/useRecorder";
import { analyzeCommittedDemo, analyzeRecording, generateDrill, getCoach } from "../lib/api";
import type { Accent, AnalysisResult, CoachResult, DemoId, SessionToneStat, Word, WordsPayload } from "../types";
import { ArrowIcon, PlayIcon, SparkIcon, VolumeIcon } from "./Icons";
import { CoDau } from "./CoDau";
import { MeaningArt } from "./MeaningArt";
import { RecordControl } from "./RecordControl";
import { SummaryModal } from "./SummaryModal";
import { ToneCurveCanvas } from "./ToneCurveCanvas";
import { ToneLegend } from "./ToneLegend";
import { ToneSyllable } from "./ToneSyllable";

type ToneLabProps = {
  payload: WordsPayload;
  accent: Accent;
  onAccentChange: (accent: Accent) => void;
  apiOnline: boolean;
};

const SESSION_KEY = "dau-session-v1";

function loadStats(): Record<string, SessionToneStat> {
  try {
    const parsed = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "{}") as { stats?: Record<string, SessionToneStat> };
    return parsed.stats ?? {};
  } catch {
    return {};
  }
}

function resultDetectedWord(result: AnalysisResult, intended: Word, words: Word[]): Word | undefined {
  const byExplicitId = wordById(result.detected_word?.id ?? result.detected_word_id ?? undefined, words);
  if (byExplicitId) return byExplicitId;
  const candidates = [intended, ...words.filter((word) => intended.minimal_pair_ids?.includes(word.id))];
  return candidates.find((word) => word.tone === result.tone_detected);
}

function fallbackCoach(result: AnalysisResult, intended: Word, payload: WordsPayload): CoachResult {
  const tone = toneById(intended.tone, payload.tones);
  const nextWord = intended.minimal_pair_ids?.find((id) => wordById(id, payload.words)?.tone === result.tone_detected) ?? intended.id;
  return {
    coaching_sentence: result.correct ? `Keep that motion: ${tone.physical_cue}` : tone.physical_cue,
    next_word: nextWord,
    rationale: result.correct ? "Add a nearby contrast while this shape feels clear." : `Repeat this contrast because your ${tone.name_en} shape drifted toward ${toneById(result.tone_detected, payload.tones).name_vi}.`,
    source: "rules",
  };
}

function verdictCopy(result: AnalysisResult, intended: Word, detected: Word | undefined): string {
  if (result.verdict_copy) return result.verdict_copy;
  if (!detected) return "Your contour landed on a different tone family.";
  if (intended.id === "phuong-name" && detected.id === "phuong-ward") return "You meant Phương, the name. You said phường, an urban ward.";
  if (intended.id === "ma-mother" && detected.id === "ma-ghost") return "You meant má, mother. You said ma, a ghost.";
  return `You meant ${intended.syllable}, ${intended.meaning_en}. You said ${detected.syllable}, ${detected.meaning_en}.`;
}

export function ToneLab({ payload, accent, onAccentChange, apiOnline }: ToneLabProps) {
  const [queue, setQueue] = useState(payload.featured_queue);
  const [selectedId, setSelectedId] = useState(payload.featured_queue[0] ?? payload.words[0]?.id);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [coach, setCoach] = useState<CoachResult | null>(null);
  const [history, setHistory] = useState<AnalysisResult[]>([]);
  const [stats, setStats] = useState<Record<string, SessionToneStat>>(loadStats);
  const [streak, setStreak] = useState(0);
  const [bestStreak, setBestStreak] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [theme, setTheme] = useState<"food" | "family" | "travel">("family");
  const [drillMessage, setDrillMessage] = useState("Featured: the Phương name test");
  const [revealKey, setRevealKey] = useState(0);
  const coachRequestRef = useRef(0);
  const currentWord = wordById(selectedId, payload.words) ?? payload.words[0];
  const target = currentWord.targets[accent];
  const intendedTone = toneById(currentWord.tone, payload.tones);
  const detectedTone = result ? toneById(result.tone_detected, payload.tones) : null;
  const detectedWord = result ? resultDetectedWord(result, currentWord, payload.words) : undefined;
  const targetAudio = useAudioPlayback();
  const fourFamilyMode = payload.scoring_modes[accent]?.includes("four") ?? accent === "south";

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ stats }));
  }, [stats]);

  const selectWord = (wordId: string) => {
    coachRequestRef.current += 1;
    setSelectedId(wordId);
    setResult(null);
    setCoach(null);
    setError(null);
  };

  const changeAccent = (nextAccent: Accent) => {
    if (nextAccent === accent) return;
    coachRequestRef.current += 1;
    setResult(null);
    setCoach(null);
    setError(null);
    onAccentChange(nextAccent);
  };

  const acceptResult = useCallback(
    (analysis: AnalysisResult, knownCoach?: CoachResult, intendedWord = currentWord) => {
      setResult(analysis);
      setRevealKey((value) => value + 1);
      setHistory((items) => [...items.slice(-22), analysis]);
      if (!analysis.needs_retry) {
        setStats((current) => {
          const prior = current[analysis.tone_intended] ?? { attempts: 0, correct: 0 };
          return { ...current, [analysis.tone_intended]: { attempts: prior.attempts + 1, correct: prior.correct + (analysis.correct ? 1 : 0) } };
        });
        setStreak((current) => {
          const next = analysis.correct ? current + 1 : 0;
          setBestStreak((best) => Math.max(best, next));
          return next;
        });
      }
      if (knownCoach) {
        setCoach(knownCoach);
        return;
      }
      // Show useful local coaching with the DSP result. The AI refinement runs
      // independently so it never extends the pitch-analysis wait.
      const requestId = coachRequestRef.current + 1;
      coachRequestRef.current = requestId;
      setCoach(fallbackCoach(analysis, intendedWord, payload));
      void getCoach(analysis, history, accent)
        .then((response) => {
          if (coachRequestRef.current === requestId) setCoach(response);
        })
        .catch(() => undefined);
    },
    [accent, currentWord, history, payload],
  );

  const onRecording = useCallback(
    async (blob: Blob) => {
      coachRequestRef.current += 1;
      setResult(null);
      setCoach(null);
      setError(null);
      try {
        const analysis = await analyzeRecording(blob, currentWord.id, currentWord.tone, accent);
        acceptResult(analysis);
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Dấu could not read that recording. Try a single clear word.");
      }
    },
    [accent, acceptResult, currentWord.id, currentWord.tone],
  );

  const recorder = useRecorder({ onRecording, silenceMs: 650, hardStopMs: 5_000 });

  const runDemo = (demoId: DemoId) => {
    const intendedId = demoId === "phuong-ward" ? "phuong-name" : "ma-mother";
    selectWord(intendedId);
    setError(null);
    const apiDemoId = demoId === "phuong-ward" ? "phuong-name-said-ward" : demoId === "ma-ghost" ? "ma-mother-said-ghost" : "ma-mother-correct";
    const intended = wordById(intendedId, payload.words)!;
    // The committed receipt makes the no-mic reveal instant, even when a hosted
    // DSP instance is still warming. Replay the WAV through the real analyzer in
    // the background and replace only the contour result when it returns.
    acceptResult(demoAnalysis(demoId, accent), demoCoach(demoId), intended);
    const requestId = coachRequestRef.current;
    void analyzeCommittedDemo(apiDemoId, intended.id, intended.tone, accent)
      .then((analysis) => {
        if (coachRequestRef.current === requestId) setResult(analysis);
      })
      .catch(() => undefined);
  };

  const moveNext = () => {
    const coachedId = coach?.next_word;
    if (coachedId && wordById(coachedId, payload.words)) {
      selectWord(coachedId);
      return;
    }
    const currentIndex = queue.indexOf(currentWord.id);
    selectWord(queue[(currentIndex + 1) % queue.length] ?? payload.words[0].id);
  };

  const newDrill = async () => {
    const nextTheme = theme === "family" ? "food" : theme === "food" ? "travel" : "family";
    setTheme(nextTheme);
    try {
      const generated = await generateDrill(nextTheme, history);
      const validIds = generated.word_ids.filter((id) => wordById(id, payload.words));
      if (validIds.length >= 3) {
        setQueue(validIds);
        selectWord(validIds[0]);
        setDrillMessage(generated.rationale);
        return;
      }
    } catch {
      // The committed sequence below is the complete no-key fallback.
    }
    const fallback = payload.drills?.[nextTheme];
    const ids = fallback?.word_ids ?? payload.featured_queue;
    setQueue(ids);
    selectWord(ids[0]);
    setDrillMessage(fallback?.title ? `${fallback.title} · committed offline drill` : "Committed offline drill");
  };

  const targetCurve = result?.target_contour?.length ? result.target_contour : target.contour;
  const learnerCurve = result?.learner_contour ?? null;
  const ghostCurve = result && !result.correct && !result.needs_retry ? (result.detected_contour ?? detectedWord?.targets[accent].contour ?? null) : null;

  const statsSummary = useMemo(() => {
    const attempts = Object.values(stats).reduce((sum, value) => sum + value.attempts, 0);
    const correct = Object.values(stats).reduce((sum, value) => sum + value.correct, 0);
    return { attempts, correct, accuracy: attempts ? Math.round((correct / attempts) * 100) : 0 };
  }, [stats]);

  const renderStageActions = (placement: "desktop" | "mobile") => (
    <div className={`stage-actions stage-actions--${placement}`}>
      <button className="target-play" type="button" onClick={() => void targetAudio.play(target.audio_url)}>
        <span>{targetAudio.playing ? <VolumeIcon /> : <PlayIcon />}</span>
        <span><small className="action-step">Step 1 · reference voice</small><strong>{targetAudio.playing ? "Watch Cô Dấu now" : "Listen + watch"}</strong><small>Hear Thầy Minh · {accent === "north" ? "Hà Nội" : "Sài Gòn"} · mirror Cô Dấu</small></span>
      </button>
      <RecordControl state={recorder.state} level={recorder.level} elapsedMs={recorder.elapsedMs} onToggle={recorder.toggle} label="Record your tone" />
    </div>
  );

  return (
    <main className="tone-lab page-enter">
      <section className="lab-toolbar" aria-label="Practice controls">
        <div className="accent-switch" role="group" aria-label="Reference accent">
          <button type="button" className={accent === "north" ? "active" : ""} onClick={() => changeAccent("north")} aria-pressed={accent === "north"}>
            Bắc <span>Hà Nội</span>
          </button>
          <button type="button" className={accent === "south" ? "active" : ""} onClick={() => changeAccent("south")} aria-pressed={accent === "south"}>
            Nam <span>Sài Gòn</span>
          </button>
        </div>
        <div className="grading-badge">
          <span className="status-dot" />
          {fourFamilyMode ? "4/6 tones auto-verified" : "6 tones auto-verified"}
        </div>
        <button type="button" className="quiet-button" onClick={() => void newDrill()}><SparkIcon /> New drill set</button>
      </section>

      <div className="practice-grid">
        <section className="contour-stage" style={{ "--active-tone": intendedTone.color } as React.CSSProperties} aria-labelledby="practice-word">
          <div className="stage-glow" aria-hidden="true" />
          <div className="word-intro">
            <p className="eyebrow">{drillMessage}</p>
            <h1 id="practice-word"><ToneSyllable text={currentWord.syllable} tone={currentWord.tone} /></h1>
            <div className="word-meta">
              <MeaningArt word={currentWord} className="word-meta__art" eager />
              <span className="word-meta__copy">
                <span><strong>{intendedTone.name_vi}</strong> · {intendedTone.name_en}</span>
                <span className="word-meta__meaning">{currentWord.meaning_en}</span>
              </span>
            </div>
          </div>

          <div className="stage-visual">
            <ToneCurveCanvas
              target={targetCurve}
              learner={learnerCurve}
              ghost={ghostCurve}
              toneColor={result && detectedTone ? detectedTone.color : intendedTone.color}
              ghostColor={detectedTone?.color}
              revealKey={revealKey}
              correct={result?.correct}
              ariaLabel={result ? `Reference ${intendedTone.name_vi} curve overlaid with your detected ${detectedTone?.name_vi} curve` : `Reference ${intendedTone.name_vi} pitch target`}
            />
            <CoDau contour={targetCurve} tone={currentWord.tone} word={currentWord.syllable} progress={targetAudio.progress} playing={targetAudio.playing} />
            {renderStageActions("mobile")}
            {recorder.state === "processing" && !result ? (
              <div className="analysis-overlay" role="status" aria-live="polite">
                <span className="analysis-overlay__orbit" aria-hidden="true"><i /></span>
                <div>
                  <small>Deterministic pitch engine</small>
                  <strong>Reading your pitch</strong>
                  <p>Extracting your voice shape, then comparing all 64 points.</p>
                  <span className="analysis-overlay__steps" aria-hidden="true"><i>pitch</i><i>shape</i><i>tone</i></span>
                </div>
              </div>
            ) : null}
          </div>

          {renderStageActions("desktop")}

          {recorder.error || error || targetAudio.error ? (
            <div className="inline-error" role="alert">
              <span>{recorder.error || error || targetAudio.error}</span>
              <button type="button" onClick={() => { recorder.clearError(); setError(null); targetAudio.clearError(); }}>Dismiss</button>
            </div>
          ) : null}

          <div className="demo-row" aria-label="No microphone samples">
            <span>No mic? Try a real sample</span>
            <button type="button" onClick={() => void runDemo("phuong-ward")}>Phương → phường</button>
            <button type="button" onClick={() => void runDemo("ma-ghost")}>má → ma</button>
            <button type="button" onClick={() => void runDemo("ma-correct")}>correct má</button>
          </div>
        </section>

        <aside className={`verdict-column ${result ? "verdict-column--shown" : ""}`} aria-live="polite">
          {!result ? (
            <div className="first-visit">
              <span className="first-visit__number">Your first tone</span>
              <h2>Watch it. Mirror it. Say it.</h2>
              <p>Cô Dấu turns pitch into a physical gesture. Follow her chin and mouth, then record one clear word.</p>
              <ol className="first-visit__steps">
                <li><span>1</span><div><strong>Listen + watch</strong><small>Mirror Cô Dấu’s head and lips.</small></div></li>
                <li><span>2</span><div><strong>Record your tone</strong><small>One tap. Say the word. Then pause.</small></div></li>
                <li><span>3</span><div><strong>See what landed</strong><small>Your curve and meaning appear together.</small></div></li>
              </ol>
              <div className="first-visit__key">
                <span className="first-visit__line"><i /> <small>reference target</small></span>
                <span className="first-visit__line first-visit__line--color"><i /> <small>your voice</small></span>
              </div>
            </div>
          ) : result.needs_retry ? (
            <div className="retry-verdict">
              <p className="eyebrow">One more take</p>
              <h2>I heard your voice, but not enough pitch to call the meaning.</h2>
              <p>{"message" in result.signal_quality ? result.signal_quality.message : "Say one word in a quiet room and hold the vowel for a beat."}</p>
              <button type="button" className="button button--primary" onClick={recorder.toggle}>Try again</button>
            </div>
          ) : result.correct ? (
            <div className="correct-verdict">
              <div className="verdict-kicker"><span>✓</span> Tone landed</div>
              <MeaningArt word={currentWord} className="correct-verdict__art" eager />
              <h2><ToneSyllable text={currentWord.syllable} tone={currentWord.tone} /> means {currentWord.meaning_en}.</h2>
              <p>Your curve moved with the reference target.</p>
              <div className="streak-pill"><strong>{streak}</strong><span>tone streak</span></div>
            </div>
          ) : (
            <div className="wrong-verdict">
              <p className="eyebrow">Tone changed the meaning</p>
              <h2>{verdictCopy(result, currentWord, detectedWord)}</h2>
              <div className="meaning-contrast">
                <div>
                  <MeaningArt word={currentWord} eager />
                  <span>you meant</span>
                  <strong><ToneSyllable text={currentWord.syllable} tone={currentWord.tone} /></strong>
                  <small>{currentWord.meaning_en}</small>
                </div>
                <div className="meaning-contrast__arrow"><ArrowIcon /></div>
                {detectedWord ? (
                  <div className="meaning-contrast__heard">
                    <MeaningArt word={detectedWord} eager />
                    <span>you said</span>
                    <strong><ToneSyllable text={detectedWord.syllable} tone={detectedWord.tone} /></strong>
                    <small>{detectedWord.meaning_en}</small>
                  </div>
                ) : null}
              </div>
              <div className="confidence-line"><span style={{ width: `${Math.round(result.confidence * 100)}%` }} /><small>{Math.round(result.confidence * 100)}% tone confidence</small></div>
            </div>
          )}

          {result && !result.needs_retry ? (
            <div className="coach-panel">
              <div className="coach-panel__label"><SparkIcon /> {coach?.source === "gpt-5.6-sol" ? "GPT-5.6 coach" : "Local tone coach"}</div>
              <p>{coach?.coaching_sentence || intendedTone.physical_cue}</p>
              <button type="button" className="next-decision" onClick={moveNext}>
                <span>Next</span>
                <strong>{wordById(coach?.next_word, payload.words)?.syllable ?? currentWord.syllable}</strong>
                <small>{coach?.rationale || "Repeat the closest contrast while the movement is fresh."}</small>
                <ArrowIcon />
              </button>
            </div>
          ) : null}
        </aside>
      </div>

      <section className="lab-footer">
        <ToneLegend
          tones={payload.tones}
          accent={accent}
          activeTone={currentWord.tone}
          onSelect={(toneId) => {
            const next = queue.find((id) => wordById(id, payload.words)?.tone === toneId) ?? payload.words.find((word) => word.tone === toneId)?.id;
            if (next) selectWord(next);
          }}
        />
        <div className="session-summary-inline">
          <div><strong>{statsSummary.attempts ? `${statsSummary.accuracy}%` : "—"}</strong><span>session</span></div>
          <div><strong>{bestStreak}</strong><span>best streak</span></div>
          <button className="quiet-button" type="button" onClick={() => setSummaryOpen(true)}>Finish session</button>
        </div>
      </section>

      <SummaryModal open={summaryOpen} onClose={() => setSummaryOpen(false)} stats={stats} streak={bestStreak} coachLine={coach?.coaching_sentence ?? ""} tones={payload.tones} />
      {!apiOnline ? <p className="sr-only" role="status">The API is offline. Committed samples are available.</p> : null}
    </main>
  );
}
