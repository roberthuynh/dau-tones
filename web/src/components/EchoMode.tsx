import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "../echo-scenes.css";
import { pedagogicalContour, toneById } from "../fallbackData";
import type { RequestMicrophoneAccess } from "../hooks/useMicrophonePrivacy";
import { useRecorder } from "../hooks/useRecorder";
import { getOrCreateReveal, transcribeEcho } from "../lib/api";
import {
  ECHO_SCENES,
  committedMistakeArt,
  findLearnerTurnForFocus,
  focusForTurn,
  fixtureAsResult,
  isOwnedEchoObjectUrl,
  learnerTurns,
  nextLearnerTurn,
  precedingPartnerTurn,
  readEchoCourseLocation,
  targetContourForFocus,
  writeEchoCourseLocation,
  type EchoCourseResult,
  type EchoScene,
  type EchoTurn,
} from "../lib/echoCourse";
import type { Accent, EchoSentence, WordsPayload } from "../types";
import { CoDau } from "./CoDau";
import { ArrowIcon, PlayIcon, SparkIcon, VolumeIcon } from "./Icons";
import { RecordControl } from "./RecordControl";
import { EchoDialogue } from "./echo/EchoDialogue";
import { EchoResultPanel } from "./echo/EchoResultPanel";
import { EchoSceneArt } from "./echo/EchoSceneArt";
import { useEchoTurnPlayback } from "./echo/useEchoTurnPlayback";

type EchoModeProps = {
  accent: Accent;
  sentences?: EchoSentence[];
  payload: WordsPayload;
  liveTranscription: boolean;
  scenes?: EchoScene[];
  onPracticeWord?: (wordId: string) => void;
  initialSceneId?: string;
  initialTurnId?: string;
  onRequestMicrophone?: RequestMicrophoneAccess;
};

const requestMicrophoneDirectly: RequestMicrophoneAccess = (_intent, action) => { void action(); };

function initialCourseLocation(scenes: EchoScene[], initialSceneId?: string, initialTurnId?: string) {
  const search = typeof window === "undefined" ? "" : window.location.search;
  const params = new URLSearchParams(search);
  const fromUrl = readEchoCourseLocation(search, scenes);
  const explicitSceneId = initialSceneId ?? params.get("scene") ?? undefined;
  const focus = params.get("focus");
  const focusMatch = focus ? findLearnerTurnForFocus(scenes, focus) : null;
  const scene = focusMatch?.scene ?? scenes.find((item) => item.id === explicitSceneId) ?? scenes.find((item) => item.id === fromUrl.sceneId) ?? scenes[0];
  const requestedTurn = focusMatch?.turn.id ?? initialTurnId ?? fromUrl.turnId;
  const learner = scene.turns.find((item) => item.id === requestedTurn && item.role === "learner") ?? nextLearnerTurn(scene);
  return {
    sceneId: scene.id,
    turnId: learner?.id ?? scene.turns[0]?.id ?? "",
    focus: focusMatch ? focus : fromUrl.focus,
  };
}

function courseTurnNumber(scenes: EchoScene[], sceneId: string, turnId: string): { current: number; total: number } {
  const allLearnerTurns = scenes.flatMap((scene) => learnerTurns(scene).map((turn) => ({ sceneId: scene.id, turnId: turn.id })));
  const index = allLearnerTurns.findIndex((item) => item.sceneId === sceneId && item.turnId === turnId);
  return { current: Math.max(1, index + 1), total: allLearnerTurns.length };
}

export function EchoMode({
  accent,
  payload,
  liveTranscription,
  scenes = ECHO_SCENES,
  onPracticeWord,
  initialSceneId,
  initialTurnId,
  onRequestMicrophone = requestMicrophoneDirectly,
}: EchoModeProps) {
  const initial = useMemo(() => initialCourseLocation(scenes, initialSceneId, initialTurnId), [initialSceneId, initialTurnId, scenes]);
  const [sceneId, setSceneId] = useState(initial.sceneId);
  const [turnId, setTurnId] = useState(initial.turnId);
  const [focusKey, setFocusKey] = useState<string | null>(initial.focus);
  const [started, setStarted] = useState(false);
  const [courseComplete, setCourseComplete] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState<string | null>(null);
  const recordingUrlRef = useRef<string | null>(null);
  const learnerAudioRef = useRef<HTMLAudioElement | null>(null);
  const [result, setResult] = useState<EchoCourseResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generatedRevealArt, setGeneratedRevealArt] = useState<string | null>(null);
  const [completedTurnIds, setCompletedTurnIds] = useState<Set<string>>(() => new Set());
  const playback = useEchoTurnPlayback();
  const playTurnAudio = playback.playTurn;
  const stopPlayback = playback.stop;

  const stopLearnerPlayback = useCallback(() => {
    if (!learnerAudioRef.current) return;
    learnerAudioRef.current.pause();
    learnerAudioRef.current.currentTime = 0;
    learnerAudioRef.current = null;
  }, []);

  const scene = scenes.find((item) => item.id === sceneId) ?? scenes[0];
  const activeTurn = scene.turns.find((item) => item.id === turnId && item.role === "learner") ?? nextLearnerTurn(scene) ?? scene.turns[0];
  const playingTurn = scene.turns.find((item) => item.id === playback.turnId) ?? activeTurn;
  const coachTurn = playback.playing ? playingTurn : activeTurn;
  const coachFocus = focusForTurn(coachTurn, playback.playing ? null : focusKey);
  const coachTone = toneById(coachFocus.tone, payload.tones);
  const targetContour = targetContourForFocus(coachFocus, accent, payload.words)
    ?? pedagogicalContour(coachFocus.tone, accent);
  const position = courseTurnNumber(scenes, scene.id, activeTurn.id);
  const sceneLearners = learnerTurns(scene);
  const sceneLearnerIndex = sceneLearners.findIndex((item) => item.id === activeTurn.id);

  const clearTake = useCallback(() => {
    stopLearnerPlayback();
    if (isOwnedEchoObjectUrl(recordingUrlRef.current)) URL.revokeObjectURL(recordingUrlRef.current!);
    recordingUrlRef.current = null;
    setRecordingUrl(null);
    setResult(null);
    setGeneratedRevealArt(null);
    setError(null);
  }, [stopLearnerPlayback]);

  const updateLocation = useCallback((nextSceneId: string, nextTurnId: string, focus?: string) => {
    if (typeof window === "undefined") return;
    window.history.replaceState({}, "", writeEchoCourseLocation(nextSceneId, nextTurnId, focus));
  }, []);

  const moveToTurn = useCallback((nextScene: EchoScene, nextTurn: EchoTurn, shouldStart: boolean, requestedFocus?: string | null) => {
    stopPlayback();
    clearTake();
    setSceneId(nextScene.id);
    setTurnId(nextTurn.id);
    const nextFocus = focusForTurn(nextTurn, requestedFocus);
    const nextFocusKey = nextFocus.word_id ?? nextFocus.token;
    setFocusKey(nextFocusKey);
    setStarted(shouldStart);
    setCourseComplete(false);
    updateLocation(nextScene.id, nextTurn.id, nextFocusKey);
  }, [clearTake, stopPlayback, updateLocation]);

  const playPartnerBefore = useCallback(async (forScene: EchoScene, learner: EchoTurn) => {
    const partner = precedingPartnerTurn(forScene, learner.id);
    if (!partner) return;
    await playTurnAudio(partner, accent);
    setCompletedTurnIds((current) => new Set(current).add(partner.id));
  }, [accent, playTurnAudio]);

  const startScene = () => {
    setStarted(true);
    setCourseComplete(false);
    const activeFocus = focusForTurn(activeTurn, focusKey);
    updateLocation(scene.id, activeTurn.id, activeFocus.word_id ?? activeFocus.token);
    void playPartnerBefore(scene, activeTurn);
  };

  const selectScene = (nextScene: EchoScene) => {
    const firstLearner = nextLearnerTurn(nextScene);
    if (!firstLearner) return;
    moveToTurn(nextScene, firstLearner, false);
  };

  useEffect(() => {
    const onPopState = () => {
      const location = readEchoCourseLocation(window.location.search, scenes);
      const nextScene = scenes.find((item) => item.id === location.sceneId) ?? scenes[0];
      const nextTurn = nextScene.turns.find((item) => item.id === location.turnId && item.role === "learner") ?? nextLearnerTurn(nextScene);
      if (nextTurn) moveToTurn(nextScene, nextTurn, false, location.focus);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [moveToTurn, scenes]);

  useEffect(() => {
    const revealId = result?.reveal_id;
    if (!revealId) return;
    let cancelled = false;
    let objectUrl: string | null = null;
    void getOrCreateReveal(revealId).then((url) => {
      objectUrl = url;
      if (!cancelled) setGeneratedRevealArt(url);
    }).catch(() => undefined);
    return () => {
      cancelled = true;
      if (objectUrl?.startsWith("blob:")) URL.revokeObjectURL(objectUrl);
    };
  }, [result]);

  useEffect(() => () => {
    stopLearnerPlayback();
    if (isOwnedEchoObjectUrl(recordingUrlRef.current)) URL.revokeObjectURL(recordingUrlRef.current!);
  }, [stopLearnerPlayback]);

  const processRecording = useCallback(async (blob: Blob) => {
    if (isOwnedEchoObjectUrl(recordingUrlRef.current)) URL.revokeObjectURL(recordingUrlRef.current!);
    const objectUrl = URL.createObjectURL(blob);
    recordingUrlRef.current = objectUrl;
    setRecordingUrl(objectUrl);
    setResult(null);
    setGeneratedRevealArt(null);
    setError(null);
    setCompletedTurnIds((current) => new Set(current).add(activeTurn.id));
    if (!liveTranscription) {
      setError("Live sentence transcription needs an OpenAI key. Replay your take beside Thầy Minh, or open the committed tone-change demo below.");
      return;
    }
    try {
      const response = await transcribeEcho(blob, activeTurn.id, accent);
      setResult({
        ...response,
        scene_id: (response as EchoCourseResult).scene_id ?? scene.id,
        turn_id: (response as EchoCourseResult).turn_id ?? activeTurn.id,
        tokens: response.tokens ?? response.diff ?? [],
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Dấu could not transcribe that line. Your recording is still ready to replay.");
    }
  }, [accent, activeTurn.id, liveTranscription, scene.id]);

  const recorder = useRecorder({
    onRecording: processRecording,
    hardStopMs: 18_000,
    silenceMs: 1_200,
    minimumMs: 1_000,
    processingTimeoutMs: 40_000,
  });
  const handleRecordToggle = () => {
    if (recorder.state === "recording") {
      recorder.stop();
      return;
    }
    if (recorder.state === "idle") onRequestMicrophone("dialogue", recorder.start);
  };

  const playCorrect = () => {
    stopLearnerPlayback();
    setError(null);
    void playTurnAudio(activeTurn, accent);
  };

  const playLearner = () => {
    if (!recordingUrl) return;
    stopPlayback();
    stopLearnerPlayback();
    setError(null);
    const audio = new Audio(recordingUrl);
    learnerAudioRef.current = audio;
    audio.addEventListener("ended", () => {
      if (learnerAudioRef.current === audio) learnerAudioRef.current = null;
    }, { once: true });
    void audio.play().catch(() => {
      if (learnerAudioRef.current === audio) learnerAudioRef.current = null;
      setError("Dấu could not replay that take. Record it once more, or use the committed demo.");
    });
  };

  const runFixture = () => {
    const fixtureTurn = scene.turns.find((item) => item.id === scene.fixture.turn_id) ?? activeTurn;
    stopPlayback();
    clearTake();
    recordingUrlRef.current = scene.fixture.audio_url;
    setRecordingUrl(scene.fixture.audio_url);
    setTurnId(fixtureTurn.id);
    const fixtureFocus = focusForTurn(fixtureTurn, scene.fixture.practice_word_ids[0]);
    const fixtureFocusKey = fixtureFocus.word_id ?? fixtureFocus.token;
    setFocusKey(fixtureFocusKey);
    setStarted(true);
    setResult(fixtureAsResult(scene));
    setGeneratedRevealArt(null);
    setCompletedTurnIds((current) => new Set(current).add(fixtureTurn.id));
    updateLocation(scene.id, fixtureTurn.id, fixtureFocusKey);
  };

  const continueCourse = () => {
    setCompletedTurnIds((current) => new Set(current).add(activeTurn.id));
    const nextInScene = nextLearnerTurn(scene, activeTurn.id);
    if (nextInScene) {
      moveToTurn(scene, nextInScene, true);
      void playPartnerBefore(scene, nextInScene);
      return;
    }
    const nextScene = scenes[scenes.findIndex((item) => item.id === scene.id) + 1];
    if (nextScene) {
      const firstLearner = nextLearnerTurn(nextScene);
      if (!firstLearner) return;
      moveToTurn(nextScene, firstLearner, true);
      void playPartnerBefore(nextScene, firstLearner);
      return;
    }
    stopPlayback();
    clearTake();
    setCourseComplete(true);
  };

  const retryActiveLine = () => {
    stopPlayback();
    clearTake();
    setCompletedTurnIds((current) => {
      const next = new Set(current);
      next.delete(activeTurn.id);
      return next;
    });
    setStarted(true);
    setCourseComplete(false);
    const activeFocus = focusForTurn(activeTurn, focusKey);
    updateLocation(scene.id, activeTurn.id, activeFocus.word_id ?? activeFocus.token);
  };

  const practiceWord = (wordId: string) => {
    if (onPracticeWord) {
      onPracticeWord(wordId);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    params.set("mode", "tones");
    params.set("word", wordId);
    params.delete("scene");
    params.delete("turn");
    params.delete("focus");
    window.location.assign(`?${params.toString()}`);
  };

  const continueLabel = sceneLearnerIndex === sceneLearners.length - 1
    ? scene.number === scenes.length ? "Finish course" : "Continue to next scene"
    : "Continue scene";
  const revealArtUrl = generatedRevealArt ?? result?.reveal_art_url ?? (result ? committedMistakeArt(result) : null);

  return (
    <main className="echo-course page-enter" style={{ "--echo-tone": coachTone.color } as React.CSSProperties}>
      <header className="echo-course__header">
        <div>
          <p className="echo-course__eyebrow">Dialogue Practice · 4 linked scenes</p>
          <h1>Use the tone in a real conversation.</h1>
          <p>Listen to Minh, answer with a complete thought, then inspect the exact mark that changed the meaning.</p>
        </div>
        <div className="echo-course__overall-progress" aria-label={`Dialogue line ${position.current} of ${position.total}`}>
          <span><strong>{String(position.current).padStart(2, "0")}</strong> / {position.total}</span>
          <div><i style={{ width: `${(position.current / position.total) * 100}%` }} /></div>
        </div>
      </header>

      <nav className="echo-course__scene-nav" aria-label="Dialogue scenes">
        {scenes.map((item) => {
          const active = item.id === scene.id;
          const complete = item.turns.filter((turn) => turn.role === "learner").every((turn) => completedTurnIds.has(turn.id));
          return (
            <button type="button" key={item.id} className={`${active ? "is-active" : ""} ${complete ? "is-complete" : ""}`} onClick={() => selectScene(item)} aria-current={active ? "step" : undefined}>
              <span>{complete ? "✓" : item.number}</span>
              <span><strong>{item.title}</strong><small>{item.subtitle}</small></span>
            </button>
          );
        })}
      </nav>

      {courseComplete ? (
        <section className="echo-course__complete">
          <span>✓</span>
          <p className="echo-course__eyebrow">Dialogue complete</p>
          <h2>You carried the tones through a whole day.</h2>
          <p>Return to any scene, replay a line, or isolate one changed word in Tone Shapes.</p>
          <button type="button" onClick={() => selectScene(scenes[0])}>Practice the story again <ArrowIcon /></button>
        </section>
      ) : (
        <div className="echo-course__workspace">
          <section className="echo-course__story">
            <EchoSceneArt key={scene.id} scene={scene} />
            <div className="echo-course__story-heading">
              <div><span>Conversation</span><strong>{scene.location}</strong></div>
              <small>{sceneLearnerIndex + 1} of {sceneLearners.length} replies</small>
            </div>
            <EchoDialogue scene={scene} activeTurn={playback.playing ? playingTurn : activeTurn} completedTurnIds={completedTurnIds} />
          </section>

          <aside className="echo-course__practice">
            <div className="echo-course__coach-row">
              <CoDau compact contour={targetContour} tone={coachFocus.tone} word={coachFocus.token} progress={playback.progress} playing={playback.playing} />
              <div className="echo-course__focus-card">
                <span>{playback.playing && playingTurn.role === "minh" ? "Mirror Minh’s focus word" : "Your focus word"}</span>
                <strong lang="vi">{coachFocus.token}</strong>
                <small>{coachTone.name_vi} · {coachTone.name_en}</small>
                <p>{coachTone.physical_cue}</p>
              </div>
            </div>

            <section className="echo-course__line-card">
              <div className="echo-course__line-meta"><span>Your line</span><small>Reply {sceneLearnerIndex + 1} of {sceneLearners.length}</small></div>
              <h2 lang="vi">{activeTurn.text}</h2>
              <p>{activeTurn.gloss_en}</p>
            </section>

            {!started ? (
              <button type="button" className="echo-course__start" onClick={startScene}>
                <PlayIcon />
                <span><strong>Start scene</strong><small>Hear Minh’s line, then answer</small></span>
                <ArrowIcon />
              </button>
            ) : (
              <>
                {playback.playing && playingTurn.role === "minh" ? (
                  <div className="echo-course__partner-playing" role="status">
                    <span><VolumeIcon /></span>
                    <div><strong>Minh is speaking</strong><small>Watch Cô Dấu follow “{playingTurn.focus.token}”</small><i><b style={{ width: `${playback.progress * 100}%` }} /></i></div>
                  </div>
                ) : null}
                {!result ? (
                  <div className="echo-course__record-area">
                    <RecordControl
                      state={recorder.state}
                      level={recorder.level}
                      elapsedMs={recorder.elapsedMs}
                      onToggle={handleRecordToggle}
                      label="Record your reply"
                      idleHint="Tap once, say the full line, then pause"
                      processingLabel="Reading the tone marks"
                      processingHint="Aligning each heard word with the dialogue"
                    />
                    <button type="button" className="echo-course__listen-line" onClick={playCorrect}><VolumeIcon /> Listen to the correct line</button>
                    {recordingUrl ? (
                      <div className="echo-course__self-review" aria-label="Recorded take review">
                        <p><strong>Your recording is ready.</strong><span>Replay both takes, then continue or open the scored demo.</span></p>
                        <div className="echo-course__replay-grid">
                          <button type="button" onClick={playLearner}><PlayIcon /><span><strong>Your take</strong><small>replay what you said</small></span></button>
                          <button type="button" onClick={playCorrect}><VolumeIcon /><span><strong>Correct take</strong><small>shadow Thầy Minh</small></span></button>
                        </div>
                        <button type="button" className="echo-course__continue echo-course__continue--unscored" onClick={continueCourse}>{continueLabel} without a score <ArrowIcon /></button>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </>
            )}

            {recorder.error || error || playback.error ? (
              <div className="echo-course__error" role="alert"><span>{recorder.error || error || playback.error}</span><button type="button" onClick={() => { recorder.clearError(); playback.clearError(); setError(null); }}>Dismiss</button></div>
            ) : null}

            {!result ? (
              <button type="button" className="echo-course__fixture" onClick={runFixture}><SparkIcon /><span><strong>No key or no Vietnamese?</strong><small>{scene.fixture.label}</small></span><ArrowIcon /></button>
            ) : (
              <EchoResultPanel
                result={result}
                words={payload.words}
                recordingUrl={recordingUrl}
                revealArtUrl={revealArtUrl}
                onPlayLearner={playLearner}
                onPlayCorrect={playCorrect}
                onPracticeWord={practiceWord}
                onRetry={retryActiveLine}
                onContinue={continueCourse}
                continuingLabel={continueLabel}
              />
            )}
          </aside>
        </div>
      )}
    </main>
  );
}
