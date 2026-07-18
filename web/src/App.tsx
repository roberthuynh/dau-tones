import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { FALLBACK_PAYLOAD } from "./fallbackData";
import { getHealth, getWords } from "./lib/api";
import { loadSoundPreference, saveSoundPreference } from "./lib/feedbackSound";
import type { Accent, HealthPayload, WordsPayload } from "./types";
import { ToneLab } from "./components/ToneLab";
import { VolumeIcon } from "./components/Icons";

const EchoMode = lazy(() => import("./components/EchoMode").then((module) => ({ default: module.EchoMode })));

type JourneyId = "tones" | "dialogue";
type SessionSummary = { attempts: number; correct: number; accuracy: number; streak: number };

function Logo() {
  return (
    <div className="brand" aria-label="Dấu home">
      <span className="brand__word">Dấu</span>
      <span className="brand__tagline">See your tones.<br />Hear what you actually said.</span>
    </div>
  );
}

function initialLocation() {
  const params = new URLSearchParams(window.location.search);
  return {
    journey: params.get("mode") === "dialogue" ? "dialogue" as JourneyId : "tones" as JourneyId,
    accent: params.get("accent") === "south" ? "south" as Accent : "north" as Accent,
    wordId: params.get("word") ?? "ma-ghost",
    sceneId: params.get("scene") ?? undefined,
    turnId: params.get("turn") ?? undefined,
  };
}

function replaceLocation(values: Partial<{ journey: JourneyId; accent: Accent; wordId: string; sceneId: string; turnId: string; focusWordId: string }>) {
  const params = new URLSearchParams(window.location.search);
  if (values.journey) params.set("mode", values.journey === "dialogue" ? "dialogue" : "tones");
  if (values.accent) params.set("accent", values.accent);
  if (values.wordId) params.set("word", values.wordId);
  if (values.sceneId) params.set("scene", values.sceneId);
  if (values.turnId) params.set("turn", values.turnId);
  if (values.focusWordId) params.set("focus", values.focusWordId);
  window.history.replaceState(null, "", `${window.location.pathname}?${params.toString()}`);
}

function SoundOffIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 10v4h4l5 4V6l-5 4H4Z" fill="currentColor" />
      <path d="m16 9 5 6m0-6-5 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export default function App() {
  const [location] = useState(initialLocation);
  const [journey, setJourney] = useState<JourneyId>(location.journey);
  const [accent, setAccent] = useState<Accent>(location.accent);
  const [selectedWordId, setSelectedWordId] = useState(location.wordId);
  const [payload, setPayload] = useState<WordsPayload>(FALLBACK_PAYLOAD);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [apiOnline, setApiOnline] = useState(true);
  const [soundEnabled, setSoundEnabled] = useState(loadSoundPreference);
  const [session, setSession] = useState<SessionSummary>({ attempts: 0, correct: 0, accuracy: 0, streak: 0 });

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([getHealth(), getWords()]).then(([healthResult, wordsResult]) => {
      if (cancelled) return;
      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
        setApiOnline(true);
      } else {
        setApiOnline(false);
      }
      if (wordsResult.status === "fulfilled" && wordsResult.value.words?.length) setPayload(wordsResult.value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const changeJourney = useCallback((next: JourneyId) => {
    setJourney(next);
    replaceLocation({ journey: next });
  }, []);

  const changeAccent = useCallback((next: Accent) => {
    setAccent(next);
    replaceLocation({ accent: next });
  }, []);

  const selectWord = useCallback((wordId: string) => {
    setSelectedWordId(wordId);
    replaceLocation({ wordId });
  }, []);

  const practiceWord = useCallback((wordId: string) => {
    setSelectedWordId(wordId);
    setJourney("tones");
    replaceLocation({ journey: "tones", wordId });
  }, []);

  const useInDialogue = useCallback((wordId: string) => {
    setJourney("dialogue");
    replaceLocation({ journey: "dialogue", focusWordId: wordId });
  }, []);

  const toggleSound = () => {
    setSoundEnabled((current) => {
      const next = !current;
      saveSoundPreference(next);
      return next;
    });
  };

  const aiCoaching = Boolean(health?.capabilities?.ai_coaching);
  const liveTranscription = Boolean(health?.capabilities?.live_echo_transcription ?? health?.capabilities?.echo_transcription);

  return (
    <div className={`app-shell ${aiCoaching ? "app-shell--keyed" : "app-shell--offline-coach"}`}>
      <a className="skip-link" href="#main-content">Skip to practice</a>
      <header className="app-header">
        <Logo />
        <nav className="journey-nav" aria-label="Learning journey">
          <button type="button" className={journey === "tones" ? "active" : ""} onClick={() => changeJourney("tones")} aria-current={journey === "tones" ? "step" : undefined}>
            <span>1</span><span><strong>Tone Shapes</strong><small>words</small></span>
          </button>
          <i aria-hidden="true" />
          <button type="button" className={journey === "dialogue" ? "active" : ""} onClick={() => changeJourney("dialogue")} aria-current={journey === "dialogue" ? "step" : undefined}>
            <span>2</span><span><strong>Dialogue Practice</strong><small>real scenes</small></span>
          </button>
        </nav>
        <div className="header-tools">
          <div className="accent-switch accent-switch--header" role="group" aria-label="Reference accent">
            <button type="button" className={accent === "north" ? "active" : ""} onClick={() => changeAccent("north")} aria-pressed={accent === "north"}>Bắc <span>Hà Nội</span></button>
            <button type="button" className={accent === "south" ? "active" : ""} onClick={() => changeAccent("south")} aria-pressed={accent === "south"}>Nam <span>Sài Gòn</span></button>
          </div>
          <button type="button" className="sound-toggle" onClick={toggleSound} aria-pressed={soundEnabled} aria-label={soundEnabled ? "Mute feedback sounds" : "Turn on feedback sounds"} title={soundEnabled ? "Sound on" : "Sound off"}>
            {soundEnabled ? <VolumeIcon /> : <SoundOffIcon />}
          </button>
          <div className="header-score" aria-label={`${session.accuracy}% session accuracy, ${session.streak} tone streak`}>
            <strong>{session.attempts ? `${session.accuracy}%` : "—"}</strong>
            <span>{session.streak ? `${session.streak} streak` : "session"}</span>
          </div>
        </div>
      </header>

      {!aiCoaching ? <div className="key-banner" role="status">Add an OpenAI key for AI coaching</div> : null}

      <div id="main-content">
        {journey === "tones" ? (
          <ToneLab
            payload={payload}
            accent={accent}
            apiOnline={apiOnline}
            soundEnabled={soundEnabled}
            initialWordId={selectedWordId}
            onWordChange={selectWord}
            onSessionUpdate={setSession}
            onUseInDialogue={useInDialogue}
          />
        ) : (
          <Suspense fallback={<div className="journey-loading" role="status"><span />Opening the dialogue…</div>}>
            <EchoMode
              accent={accent}
              payload={payload}
              liveTranscription={liveTranscription}
              onPracticeWord={practiceWord}
              initialSceneId={location.sceneId}
              initialTurnId={location.turnId}
            />
          </Suspense>
        )}
      </div>

      <footer className="app-footer">
        <span>Dấu is open source · deterministic pitch grading</span>
        <span>DSP judges. GPT-5.6 coaches.</span>
      </footer>
    </div>
  );
}
