import { useEffect, useState } from "react";
import { FALLBACK_ECHO_SENTENCES, FALLBACK_PAYLOAD } from "./fallbackData";
import { getEchoSentences, getHealth, getWords, warmAnalysis } from "./lib/api";
import type { Accent, EchoSentence, HealthPayload, WordsPayload } from "./types";
import { EchoMode } from "./components/EchoMode";
import { ToneLab } from "./components/ToneLab";

type TabId = "lab" | "echo";

function Logo() {
  return (
    <div className="brand" aria-label="Dấu home">
      <span className="brand__word">Dấu</span>
      <span className="brand__mark" aria-hidden="true">´</span>
      <span className="brand__tagline">See your tones.<br />Hear what you actually said.</span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState<TabId>("lab");
  const [accent, setAccent] = useState<Accent>("north");
  const [payload, setPayload] = useState<WordsPayload>(FALLBACK_PAYLOAD);
  const [sentences, setSentences] = useState<EchoSentence[]>(FALLBACK_ECHO_SENTENCES);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [apiOnline, setApiOnline] = useState(true);
  const [analysisWarm, setAnalysisWarm] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Compile pYIN while the learner reads the first prompt. This is deliberately
    // fire-and-forget so readiness data and the interface never wait on warmup.
    void warmAnalysis()
      .then(() => {
        if (!cancelled) setAnalysisWarm(true);
      })
      .catch(() => undefined);
    void Promise.allSettled([getHealth(), getWords(), getEchoSentences()]).then(([healthResult, wordsResult, echoResult]) => {
      if (cancelled) return;
      if (healthResult.status === "fulfilled") {
        setHealth(healthResult.value);
        setApiOnline(true);
      } else setApiOnline(false);
      if (wordsResult.status === "fulfilled" && wordsResult.value.words?.length) setPayload(wordsResult.value);
      if (echoResult.status === "fulfilled" && echoResult.value.length) setSentences(echoResult.value);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const aiCoaching = Boolean(health?.capabilities?.ai_coaching);
  const liveTranscription = Boolean(health?.capabilities?.live_echo_transcription ?? health?.capabilities?.echo_transcription);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to practice</a>
      <header className="app-header">
        <Logo />
        <nav className="mode-tabs" aria-label="Practice mode">
          <button type="button" className={tab === "lab" ? "active" : ""} onClick={() => setTab("lab")} aria-current={tab === "lab" ? "page" : undefined}>
            Tone Lab <span>words</span>
          </button>
          <button type="button" className={tab === "echo" ? "active" : ""} onClick={() => setTab("echo")} aria-current={tab === "echo" ? "page" : undefined}>
            Echo <span>sentences</span>
          </button>
        </nav>
        <div
          className="header-status"
          title={apiOnline ? (analysisWarm ? "Pitch engine is warm" : "Pitch engine is warming in the background") : "API offline, samples still work"}
        >
          <span className={apiOnline ? "online" : "offline"} />
          {apiOnline ? (analysisWarm ? "DSP ready" : "warming pitch") : "demo mode"}
        </div>
      </header>

      {health && !aiCoaching ? <div className="key-banner" role="status">Add an OpenAI key for AI coaching</div> : null}

      <div id="main-content">
        {tab === "lab" ? (
          <ToneLab payload={payload} accent={accent} onAccentChange={setAccent} apiOnline={apiOnline} />
        ) : (
          <EchoMode accent={accent} sentences={sentences} payload={payload} liveTranscription={liveTranscription} />
        )}
      </div>

      <footer className="app-footer">
        <span>Dấu is open source · deterministic pitch grading</span>
        <span>DSP judges. GPT-5.6 coaches.</span>
      </footer>
    </div>
  );
}
