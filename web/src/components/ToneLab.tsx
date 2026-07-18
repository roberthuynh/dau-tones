import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { demoAnalysis, demoCoach, toneById, wordById } from "../fallbackData";
import { useAudioPlayback } from "../hooks/useAudioPlayback";
import { useRecorder } from "../hooks/useRecorder";
import { generateDrill, getCoach } from "../lib/api";
import { playFeedbackSound } from "../lib/feedbackSound";
import { analyzeLocally } from "../lib/localDsp";
import { familyLabel, signedSemitones, toneSurfaceForWord, TONE_MARK_LABEL } from "../lib/toneLanguage";
import type {
  Accent,
  AnalysisResult,
  CoachResult,
  DemoId,
  SemanticStatus,
  SessionToneStat,
  Word,
  WordsPayload,
} from "../types";
import { ArrowIcon, PlayIcon, SparkIcon, VolumeIcon } from "./Icons";
import { CoDau } from "./CoDau";
import { MaToneRail } from "./MaToneRail";
import { MeaningArt } from "./MeaningArt";
import { RecordControl } from "./RecordControl";
import { SummaryModal } from "./SummaryModal";
import { ToneCurveCanvas } from "./ToneCurveCanvas";
import { ToneSyllable } from "./ToneSyllable";

type ToneLabProps = {
  payload: WordsPayload;
  accent: Accent;
  apiOnline: boolean;
  soundEnabled: boolean;
  initialWordId?: string;
  onWordChange?: (wordId: string) => void;
  onSessionUpdate?: (summary: { attempts: number; correct: number; accuracy: number; streak: number }) => void;
  onUseInDialogue?: (wordId: string) => void;
};

type RichCoach = CoachResult & { observation?: string };

const SESSION_KEY = "dau-session-v2";
const MA_IDS = ["ma-ghost", "ma-but", "ma-mother", "ma-grave", "ma-code", "ma-seedling"];
const PHUONG_IDS = ["phuong-name", "phuong-ward", "phuong-phoenix"];

const PHYSICAL_TIPS: Record<string, string> = {
  started_too_high: "Drop your starting point, then move into the tone without pushing.",
  started_too_low: "Begin a little higher so the vowel has room to travel.",
  ended_too_low: "Keep your chin from sinking at the end and carry the vowel to the target height.",
  ended_too_high: "Let your chin settle sooner so the ending does not float above the target.",
  no_final_rise: "Keep the vowel open, lift your chin, and finish the rise instead of stopping halfway.",
  fell_instead_of_level: "Hold your chin still and send the vowel straight ahead from start to finish.",
  too_flat: "Make the pitch movement larger while keeping the vowel relaxed.",
  missing_dip: "Let your chin fall through the middle, then recover before the vowel ends.",
  dip_too_early: "Hold the opening briefly; place the dip in the middle, then recover.",
  dip_too_late: "Begin the dip sooner so there is time to recover at the end.",
  weak_glottal_break: "Add one brief throat catch, then release the vowel into its final movement.",
  weak_energy_dip: "Briefly tighten at the throat so the catch is audible, then release.",
  too_long: "Shorten the vowel and close it firmly with your throat.",
  too_short: "Hold the vowel for one comfortable beat so the full shape can appear.",
  shape_drifted: "Trace the gray line with your chin and keep the vowel steady while the pitch moves.",
};

function loadStats(): Record<string, SessionToneStat> {
  try {
    const parsed = JSON.parse(localStorage.getItem(SESSION_KEY) ?? "{}") as { stats?: Record<string, SessionToneStat> };
    return parsed.stats ?? {};
  } catch {
    return {};
  }
}

function groupWords(intended: Word, words: Word[]): Word[] {
  if (intended.id.startsWith("ma-")) return words.filter((word) => word.id.startsWith("ma-"));
  if (intended.id.startsWith("phuong-")) return words.filter((word) => word.id.startsWith("phuong-"));
  return [intended, ...words.filter((word) => intended.minimal_pair_ids?.includes(word.id))];
}

function resultDetectedWord(result: AnalysisResult, intended: Word, words: Word[]): Word | undefined {
  const byExplicitId = wordById(result.meaning_verdict.detected_word_id ?? result.detected_word?.id ?? result.detected_word_id ?? undefined, words);
  if (byExplicitId) return byExplicitId;
  return groupWords(intended, words).find((word) => word.tone === result.tone_detected);
}

function resultStatus(result: AnalysisResult): SemanticStatus {
  if (result.needs_retry) return "uncertain";
  return result.semantic_status;
}

function statusIsCorrect(status: SemanticStatus): boolean {
  return status === "exact_correct" || status === "family_correct";
}

function observationFor(result: AnalysisResult, intended: Word, payload: WordsPayload): string {
  const numeric = result.tips_features.numeric;
  const codes = result.tips_features.codes;
  const first = codes[0];
  if (first === "ended_too_low" && Number.isFinite(numeric.end)) {
    return `Your ending fell ${signedSemitones(numeric.end)} below the ${toneById(intended.tone, payload.tones).name_en} target.`;
  }
  if (first === "ended_too_high" && Number.isFinite(numeric.end)) {
    return `Your ending stayed ${signedSemitones(numeric.end)} above the target.`;
  }
  if (first === "started_too_high" && Number.isFinite(numeric.start)) {
    return `Your opening began ${signedSemitones(numeric.start)} above the target.`;
  }
  if (first === "started_too_low" && Number.isFinite(numeric.start)) {
    return `Your opening began ${signedSemitones(numeric.start)} below the target.`;
  }
  if (first === "no_final_rise" && Number.isFinite(numeric.slope)) {
    return `Your pitch traveled ${signedSemitones(numeric.slope)} less upward than the target.`;
  }
  if (Number.isFinite(numeric.dip_position)) {
    const direction = numeric.dip_position < 0 ? "earlier" : "later";
    return `Your lowest point arrived ${Math.abs(numeric.dip_position * 100).toFixed(0)}% ${direction} than the target.`;
  }
  if (statusIsCorrect(resultStatus(result))) {
    return `Your full contour stayed closest to ${toneById(intended.tone, payload.tones).name_vi} with ${Math.round(result.class_confidence * 100)}% class confidence.`;
  }
  return `Your closest shape was ${toneById(result.tone_detected, payload.tones).name_vi}, not ${toneById(intended.tone, payload.tones).name_vi}.`;
}

function fallbackCoach(result: AnalysisResult, intended: Word, payload: WordsPayload): RichCoach {
  const status = resultStatus(result);
  const tone = toneById(intended.tone, payload.tones);
  const detected = resultDetectedWord(result, intended, payload.words);
  const nextWord = !statusIsCorrect(status) && detected?.id !== intended.id ? detected?.id ?? intended.id : intended.minimal_pair_ids?.[0] ?? intended.id;
  const firstTip = result.tips_features.codes.find((code) => PHYSICAL_TIPS[code]);
  return {
    observation: observationFor(result, intended, payload),
    coaching_sentence: firstTip ? PHYSICAL_TIPS[firstTip] : statusIsCorrect(status) ? `Keep that exact motion: ${tone.physical_cue}` : tone.physical_cue,
    next_word: nextWord,
    rationale: statusIsCorrect(status)
      ? "Use the nearest meaning contrast while this shape is still physical."
      : `Contrast ${intended.syllable} with ${detected?.syllable ?? toneSurfaceForWord(intended, result.tone_detected)} because that is where your last contour landed.`,
    source: "rules",
  };
}

type VerdictPanelProps = {
  result: AnalysisResult;
  currentWord: Word;
  detectedWord?: Word;
  payload: WordsPayload;
  streak: number;
  onRetry: () => void;
};

function VerdictPanel({ result, currentWord, detectedWord, payload, streak, onRetry }: VerdictPanelProps) {
  const status = resultStatus(result);
  const detectedTone = toneById(result.tone_detected, payload.tones);
  const heardSurface = result.meaning_verdict.detected_surface ?? toneSurfaceForWord(currentWord, result.tone_detected);
  const classPercent = Math.round(result.class_confidence * 100);

  if (status === "uncertain") {
    return (
      <section className="tone-verdict tone-verdict--retry">
        <span className="tone-verdict__symbol">↺</span>
        <div>
          <p className="eyebrow">One more clear take</p>
          <h2>No meaning called</h2>
          <p>{"message" in result.signal_quality ? result.signal_quality.message : "Hold one vowel for a comfortable beat in a quieter spot."}</p>
          <button type="button" className="button button--primary" onClick={onRetry}>Record again</button>
        </div>
      </section>
    );
  }

  if (status === "exact_correct" || status === "family_correct") {
    return (
      <section className="tone-verdict tone-verdict--correct">
        <span className="tone-verdict__symbol" aria-hidden="true">✓</span>
        <div className="tone-verdict__copy">
          <p className="eyebrow">{status === "exact_correct" ? "Six-tone match" : "Acoustic family verified"}</p>
          <h2>{status === "exact_correct" ? "Correct" : "Correct family"} · {currentWord.syllable} · {TONE_MARK_LABEL[currentWord.tone]}</h2>
          <p>{currentWord.syllable} means <strong>{currentWord.meaning_en}</strong>.</p>
          <div className="tone-verdict__reward">
            <MeaningArt word={currentWord} eager />
            <span><strong>{streak}</strong> tone streak</span>
          </div>
        </div>
      </section>
    );
  }

  if (status === "family_ambiguous") {
    return (
      <section className="tone-verdict tone-verdict--ambiguous">
        <span className="tone-verdict__symbol" aria-hidden="true">≈</span>
        <div className="tone-verdict__copy">
          <p className="eyebrow">Family matched · exact tone uncertain</p>
          <h2>The {familyLabel(result.intended_family)} family matched; the closest exact shape was {TONE_MARK_LABEL[result.tone_detected]}.</h2>
          <p>Try once more before Dấu assigns a different meaning.</p>
          <div className="tone-verdict__confidence"><i style={{ width: `${classPercent}%` }} /><span>{classPercent}% class confidence</span></div>
        </div>
      </section>
    );
  }

  return (
    <section className="tone-verdict tone-verdict--wrong">
      <span className="tone-verdict__symbol" aria-hidden="true">×</span>
      <div className="tone-verdict__copy">
        <p className="eyebrow">Tone changed what was heard</p>
        <h2>Heard: {heardSurface} · {TONE_MARK_LABEL[result.tone_detected]} · {detectedTone.name_en}</h2>
        {status === "wrong_known_word" && detectedWord ? (
          <div className="meaning-comparison">
            <div>
              <MeaningArt word={currentWord} eager />
              <span>you meant</span>
              <strong>{currentWord.syllable}</strong>
              <small>{currentWord.meaning_en}</small>
            </div>
            <ArrowIcon />
            <div className="meaning-comparison__heard">
              <MeaningArt word={detectedWord} eager />
              <span>Dấu heard</span>
              <strong>{heardSurface}</strong>
              <small>{detectedWord.meaning_en}</small>
            </div>
          </div>
        ) : (
          <div className="no-known-meaning">
            <strong>{heardSurface}</strong>
            <p>Dấu heard {TONE_MARK_LABEL[result.tone_detected]} on “{currentWord.syllable}.” That form has no curated meaning in this lesson.</p>
          </div>
        )}
        <div className="tone-verdict__confidence"><i style={{ width: `${classPercent}%` }} /><span>{classPercent}% class confidence</span></div>
      </div>
    </section>
  );
}

type CoachPanelProps = {
  coach: RichCoach | null;
  currentWord: Word;
  payload: WordsPayload;
  onNext: () => void;
  onUseInDialogue?: (wordId: string) => void;
};

function CoachPanel({ coach, currentWord, payload, onNext, onUseInDialogue }: CoachPanelProps) {
  const next = wordById(coach?.next_word, payload.words) ?? currentWord;
  return (
    <section className="coach-decision">
      <div className="coach-decision__label"><SparkIcon /> {coach?.source === "gpt-5.6-sol" ? "GPT-5.6 coach" : "Instant local coach"}</div>
      {coach?.observation ? <p className="coach-decision__observation">{coach.observation}</p> : null}
      <p className="coach-decision__instruction">{coach?.coaching_sentence ?? toneById(currentWord.tone, payload.tones).physical_cue}</p>
      <button type="button" className="next-decision" onClick={onNext}>
        <span>Next shape</span>
        <strong>{next.syllable}</strong>
        <small>{coach?.rationale ?? "Repeat the closest contrast while the movement is fresh."}</small>
        <ArrowIcon />
      </button>
      {onUseInDialogue ? <button type="button" className="coach-decision__dialogue" onClick={() => onUseInDialogue(currentWord.id)}>Use this tone in Dialogue Practice <ArrowIcon /></button> : null}
    </section>
  );
}

export function ToneLab({
  payload,
  accent,
  apiOnline,
  soundEnabled,
  initialWordId,
  onWordChange,
  onSessionUpdate,
  onUseInDialogue,
}: ToneLabProps) {
  const defaultId = initialWordId && wordById(initialWordId, payload.words) ? initialWordId : MA_IDS.find((id) => wordById(id, payload.words)) ?? payload.words[0]?.id;
  const [queue, setQueue] = useState(payload.featured_queue);
  const [selectedId, setSelectedId] = useState(defaultId);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [coach, setCoach] = useState<RichCoach | null>(null);
  const [history, setHistory] = useState<AnalysisResult[]>([]);
  const [stats, setStats] = useState<Record<string, SessionToneStat>>(loadStats);
  const [streak, setStreak] = useState(0);
  const [bestStreak, setBestStreak] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [theme, setTheme] = useState<"food" | "family" | "travel">("family");
  const [drillMessage, setDrillMessage] = useState("The six shapes of ma");
  const [revealKey, setRevealKey] = useState(0);
  const coachRequestRef = useRef(0);
  const currentWord = wordById(selectedId, payload.words) ?? payload.words[0];
  const target = currentWord.targets[accent];
  const intendedTone = toneById(currentWord.tone, payload.tones);
  const detectedTone = result ? toneById(result.tone_detected, payload.tones) : null;
  const detectedWord = result ? resultDetectedWord(result, currentWord, payload.words) : undefined;
  const targetAudio = useAudioPlayback();
  const fourFamilyMode = payload.scoring_modes[accent]?.includes("four") ?? accent === "south";

  const statsSummary = useMemo(() => {
    const attempts = Object.values(stats).reduce((sum, value) => sum + value.attempts, 0);
    const correct = Object.values(stats).reduce((sum, value) => sum + value.correct, 0);
    return { attempts, correct, accuracy: attempts ? Math.round((correct / attempts) * 100) : 0 };
  }, [stats]);

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ stats }));
  }, [stats]);

  useEffect(() => {
    onSessionUpdate?.({ ...statsSummary, streak: bestStreak });
  }, [bestStreak, onSessionUpdate, statsSummary]);

  const selectWord = useCallback((wordId: string) => {
    coachRequestRef.current += 1;
    setSelectedId(wordId);
    setResult(null);
    setCoach(null);
    setError(null);
    onWordChange?.(wordId);
  }, [onWordChange]);

  const acceptResult = useCallback(
    (analysis: AnalysisResult, knownCoach?: RichCoach, intendedWord = currentWord) => {
      const status = resultStatus(analysis);
      const successful = statusIsCorrect(status);
      setResult(analysis);
      setRevealKey((value) => value + 1);
      setHistory((items) => [...items.slice(-22), analysis]);
      if (status !== "uncertain") {
        setStats((current) => {
          const prior = current[analysis.tone_intended] ?? { attempts: 0, correct: 0 };
          return { ...current, [analysis.tone_intended]: { attempts: prior.attempts + 1, correct: prior.correct + (successful ? 1 : 0) } };
        });
        setStreak((current) => {
          const next = successful ? current + 1 : 0;
          setBestStreak((best) => Math.max(best, next));
          return next;
        });
        playFeedbackSound(successful ? "correct" : status === "family_ambiguous" ? "ambiguous" : "wrong", soundEnabled);
      }
      const localCoach = knownCoach ?? fallbackCoach(analysis, intendedWord, payload);
      setCoach(localCoach);
      if (knownCoach) return;
      const requestId = coachRequestRef.current + 1;
      coachRequestRef.current = requestId;
      void getCoach(analysis, history, accent)
        .then((response) => {
          if (coachRequestRef.current === requestId) setCoach({ ...response, observation: response.observation ?? localCoach.observation });
        })
        .catch(() => undefined);
    },
    [accent, currentWord, history, payload, soundEnabled],
  );

  const onRecording = useCallback(
    async (blob: Blob) => {
      coachRequestRef.current += 1;
      setResult(null);
      setCoach(null);
      setError(null);
      try {
        acceptResult(await analyzeLocally(blob, currentWord, accent, payload));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : "Dấu could not read that recording. Try one clear word.");
      }
    },
    [accent, acceptResult, currentWord, payload],
  );

  const recorder = useRecorder({ onRecording, silenceMs: 520, hardStopMs: 4_200, processingTimeoutMs: 5_000 });

  const runDemo = useCallback((demoId: DemoId) => {
    const intendedId = demoId === "phuong-ward" ? "phuong-name" : "ma-mother";
    const intended = wordById(intendedId, payload.words);
    if (!intended) return;
    selectWord(intendedId);
    const receipt = demoAnalysis(demoId, accent);
    acceptResult(receipt, { ...demoCoach(demoId), observation: observationFor(receipt, intended, payload) }, intended);
  }, [accent, acceptResult, payload, selectWord]);

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
      // The committed sequence below completes the same loop without a key.
    }
    const fallback = payload.drills?.[nextTheme];
    const ids = fallback?.word_ids ?? payload.featured_queue;
    setQueue(ids);
    selectWord(ids[0]);
    setDrillMessage(fallback?.title ? `${fallback.title} · offline drill` : "Committed offline drill");
  };

  const status = result ? resultStatus(result) : null;
  const targetCurve = result?.target_contour?.length ? result.target_contour : target.contour;
  const learnerCurve = result?.learner_contour ?? null;
  const showGhost = Boolean(result && status && !statusIsCorrect(status) && status !== "uncertain");
  const ghostCurve = showGhost ? (result?.detected_contour ?? detectedWord?.targets[accent].contour ?? null) : null;
  const moreWords = [...PHUONG_IDS, ...payload.words.map((word) => word.id).filter((id) => !MA_IDS.includes(id) && !PHUONG_IDS.includes(id))]
    .map((id) => wordById(id, payload.words))
    .filter((word): word is Word => Boolean(word));

  return (
    <main className="tone-lab page-enter">
      <MaToneRail words={payload.words} tones={payload.tones} accent={accent} activeWordId={currentWord.id} onSelect={selectWord} />

      <div className="tone-workbench" style={{ "--active-tone": intendedTone.color } as React.CSSProperties}>
        <section className="tone-workbench__practice" aria-labelledby="practice-word">
          <div className="lesson-heading">
            <div>
              <p className="eyebrow">{currentWord.id.startsWith("ma-") ? "The complete ma lesson" : drillMessage}</p>
              <h1 id="practice-word"><ToneSyllable text={currentWord.syllable} tone={currentWord.tone} /></h1>
            </div>
            <div className="word-definition">
              <MeaningArt word={currentWord} className="word-definition__art" eager />
              <span><strong>{currentWord.syllable}</strong><small>{currentWord.meaning_en}</small><em>{intendedTone.name_vi} · {TONE_MARK_LABEL[currentWord.tone]}</em></span>
            </div>
          </div>

          <div className={`curve-stage ${result && status ? `curve-stage--${status}` : ""}`}>
            <ToneCurveCanvas
              target={targetCurve}
              learner={learnerCurve}
              ghost={ghostCurve}
              toneColor={result && detectedTone ? detectedTone.color : intendedTone.color}
              ghostColor={detectedTone?.color}
              revealKey={revealKey}
              correct={Boolean(status && statusIsCorrect(status))}
              targetLabel={target.validated ? "validated native target" : "shape preview · phone target pending"}
              ariaLabel={result ? `Reference ${intendedTone.name_vi} curve overlaid with your closest ${detectedTone?.name_vi} curve` : `${intendedTone.name_vi} pitch shape`}
            />
            {recorder.state === "processing" && !result ? <div className="analysis-chip" role="status"><span /><strong>Grading locally</strong><small>pitch · shape · meaning</small></div> : null}
          </div>

          <div className="tone-actions">
            <button
              className="target-play"
              type="button"
              onClick={() => target.audio_url && void targetAudio.play(target.audio_url)}
              disabled={!target.validated || !target.audio_url}
            >
              <span>{targetAudio.playing ? <VolumeIcon /> : <PlayIcon />}</span>
              <span>
                <small className="action-step">1 · Reference</small>
                <strong>{target.validated ? (targetAudio.playing ? "Mirror Cô Dấu now" : "Listen + watch") : "Phone target needed"}</strong>
                <small>{target.validated ? `Thầy Minh · ${accent === "north" ? "Hà Nội" : "Sài Gòn"}` : "This tone remains visible, but it is not graded until validation passes."}</small>
              </span>
            </button>
            <RecordControl
              state={recorder.state}
              level={recorder.level}
              elapsedMs={recorder.elapsedMs}
              onToggle={recorder.toggle}
              label="Record your tone"
              processingLabel="Grading on this device"
              processingHint="Usually under one second · no upload"
              disabled={!target.validated}
            />
          </div>

          {recorder.error || error || targetAudio.error ? (
            <div className="inline-error" role="alert">
              <span>{recorder.error || error || targetAudio.error}</span>
              <button type="button" onClick={() => { recorder.clearError(); setError(null); targetAudio.clearError(); }}>Dismiss</button>
            </div>
          ) : null}

          <div className="practice-shortcuts">
            <span>No mic? Run a scored sample:</span>
            <button type="button" onClick={() => runDemo("ma-correct")}>✓ correct má</button>
            <button type="button" onClick={() => runDemo("ma-ghost")}>má → ma · ghost</button>
            <button type="button" onClick={() => runDemo("phuong-ward")}>Phương → phường · ward</button>
          </div>
        </section>

        <aside className={`teacher-rail ${result ? "teacher-rail--has-result" : ""}`} aria-live="polite">
          <div className="teacher-rail__avatar">
            <CoDau contour={targetCurve} tone={currentWord.tone} word={currentWord.syllable} progress={targetAudio.progress} playing={targetAudio.playing} />
          </div>
          <div className="teacher-rail__feedback">
            {!result ? (
              <section className="teacher-start">
                <p className="eyebrow">Watch · mirror · say it</p>
                <h2>Move your face with the line.</h2>
                <p>Listen once. Follow Cô Dấu’s chin, lips, and throat. Then record one clear word.</p>
                <div><span>1</span> Hear the target <i /> <span>2</span> Mirror the motion <i /> <span>3</span> See what landed</div>
              </section>
            ) : (
              <>
                <VerdictPanel result={result} currentWord={currentWord} detectedWord={detectedWord} payload={payload} streak={streak} onRetry={recorder.toggle} />
                {status !== "uncertain" ? <CoachPanel coach={coach} currentWord={currentWord} payload={payload} onNext={moveNext} onUseInDialogue={onUseInDialogue} /> : null}
              </>
            )}
          </div>
        </aside>
      </div>

      <section className="more-words" aria-label="More practice words">
        <div>
          <p className="eyebrow">More words</p>
          <strong>Next, test the name Phương and everyday vocabulary.</strong>
        </div>
        <div className="more-words__rail">
          {moreWords.map((word) => (
            <button type="button" className={word.id === currentWord.id ? "active" : ""} onClick={() => selectWord(word.id)} key={word.id}>
              <ToneSyllable text={word.syllable} tone={word.tone} /><small>{word.meaning_en}</small>
            </button>
          ))}
        </div>
        <button type="button" className="quiet-button" onClick={() => void newDrill()}><SparkIcon /> New drill set</button>
        <div className="session-summary-inline">
          <div><strong>{statsSummary.attempts ? `${statsSummary.accuracy}%` : "—"}</strong><span>session</span></div>
          <div><strong>{bestStreak}</strong><span>best streak</span></div>
          <button className="quiet-button" type="button" onClick={() => setSummaryOpen(true)}>Finish</button>
        </div>
      </section>

      <SummaryModal open={summaryOpen} onClose={() => setSummaryOpen(false)} stats={stats} streak={bestStreak} coachLine={coach?.coaching_sentence ?? ""} tones={payload.tones} />
      <p className="grading-disclosure">{fourFamilyMode ? `${accent === "north" ? "Northern" : "Southern"} profile: four acoustic families; the closest exact form remains visible.` : "Northern profile: six exact tones when the corpus gate passes."}</p>
      {!apiOnline ? <p className="sr-only" role="status">The coaching API is offline. Local pitch grading and committed lessons remain available.</p> : null}
    </main>
  );
}
