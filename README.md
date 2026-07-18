# Dấu

> See your tones. Hear what you actually said.

Dấu is an open-source practice lab that makes Vietnamese tones visible by drawing a learner's pitch over a validated native target. Local signal processing grades the contour, then a tone coach explains the physical correction and shows the real meaning a wrong tone can create.

**Demo video:** [Build Week submission video coming soon](https://github.com/roberthuynh/dau-tones)

![Dấu Tone Lab showing the Phương to phường meaning verdict](web/public/screenshots/tone-lab-phuong.jpg)

## Quick start

```bash
git clone https://github.com/roberthuynh/dau-tones.git
cd dau-tones
./dev.sh
```

Wait for `READY http://localhost:5173`, then open that URL. The script installs an uv-managed Python 3.11 environment and locked npm dependencies, warms pYIN, and starts FastAPI on port 8000 plus Vite on port 5173. Node.js 22+ and either `uv` or `curl` are the only host requirements.

No OpenAI key is required for local grading, target playback, committed meaning art, deterministic coaching, analyzer demos, or cached Echo shadowing. With a key, server-only AI coaching and live Echo features turn on automatically:

```bash
cp .env.example .env.local
# Put OPENAI_API_KEY in .env.local. Never expose it through a VITE_ variable.
./dev.sh
```

The same monorepo deploys as one Vercel project: the Vite service owns `/`, the FastAPI service owns `/api`, and the secret remains scoped to the Python service. The native pYIN, SciPy, LLVM, and PyAV stack uses [Vercel Large Functions](https://vercel.com/changelog/python-vercel-functions-bundle-size-limit-increased-to-500mb); the verified 568 MB Python bundle keeps the same DSP and browser-audio decoding in production.

GitHub Actions is manual-only during the build to preserve the free-plan quota. The same lint, test, build, and offline end-to-end checks run locally before each published milestone.

## How it works

1. `gpt-realtime-2.1` speaks five Cedar candidates for every target in Northern and Southern Vietnamese. The same DSP used for learners rejects acoustically invalid candidates before one take can become ground truth.
2. `librosa.pyin` extracts F0, fills valid unvoiced gaps, normalizes pitch into speaker-relative semitones, and resamples each contour to 64 points. A deterministic template matcher grades shape, timing, energy, and voicing evidence.
3. `gpt-5.6-sol` runs only on the FastAPI server for specific coaching, next-drill selection with visible reasoning, themed ordering of validated words, and Echo meaning explanations. Rule-based coaching covers the same loop when no key is present.
4. `gpt-4o-transcribe` runs server-side for keyed Echo transcription. `gpt-realtime-2.1-mini` generates bounded Echo shadowing speech, while validated drill audio always comes from the committed reference corpus.
5. `gpt-image-2` generates the committed word illustrations at build time and one optional literal wrong-sentence reveal at runtime. The browser never receives an OpenAI key.

Audio language models are poor judges of pitch shape, so the DSP judges and the LLM coaches. Pitch grading is deterministic and inspectable; GPT-5.6 handles the work it is better at: concrete instruction, drill choice, and meaning. Stage 6 measures this claim in-repo by asking the sibling Realtime model to name the tones in its own validated speech and comparing it with the leakage-safe DSP evaluation.

Active model IDs live in one API config module:

| Job | Model |
| --- | --- |
| Coaching, drills, explanations | `gpt-5.6-sol` |
| Meaning and Echo reveal art | `gpt-image-2` |
| Echo transcription | `gpt-4o-transcribe` |
| Echo speech | `gpt-realtime-2.1-mini` |
| Reference targets and benchmark | `gpt-realtime-2.1` |

## Built with Codex

This task is the build log and scored Codex artifact. The repository is pushed as verified stages land so the history records the product being made, not a final code dump.

| Stage | What Codex accelerated | Key decision and owner |
| --- | --- | --- |
| Repository | Product plan, safety boundaries, offline contract, and incremental publishing | Robert required MIT in commit 1 and direct pushes to `main`; Codex set the verification gates. |
| Cold start | Locked Python/Node installs, pYIN warming, dual-process supervision, manual CI, and a one-project Vercel service map | Robert added Vercel deployment; Codex kept local and hosted URLs on the same `/api` contract and preserved the full DSP stack with Large Functions. |
| Voice design | Dual-accent target generation and DSP acceptance design | Robert chose Cedar and supplied the exact Sài Gòn and Hà Nội voice prompts. |
| Grading | Accent-conditioned acoustic families and honest uncertainty | Robert required six visible tones; Codex recommended Northern evaluation-gated six-way grading and Southern four-family auto-verification. |
| DSP engine | Browser-media decoding, speech-island checks, pYIN, speaker-relative contours, constrained DTW, feature distance, confidence, abstention, and grouped-fold evaluation | Codex made intended tone unavailable to detection and capped confidence at 0.95; Robert chose the dual-accent product behavior. |
| API | Typed analysis, fallback and GPT coaching, validated drill selection, NFC Echo alignment, cached speech, capability flags, and human error responses | Codex kept every AI client lazy and server-only; Robert required the complete loop to survive with no key. |
| Meaning art | Nineteen cached `gpt-image-2` illustrations, locked prompts, hashes, and a contact-sheet audit | Robert made wrong-meaning pictures load-bearing; Codex kept generation build-time, one-shot, and fully available offline. |
| Tone Lab | Canvas contour choreography, microphone silence-stop, meaning verdicts, session summaries, responsive layouts, and the code-native Cô Dấu coach | Robert specified the dark theatre and signature Phương moment; Codex implemented and browser-tested the full loop at desktop and mobile sizes. |

More decisions and measured results will be added with each stage.

## Evaluation

All reported product metrics will come from committed artifacts generated by `python -m api.eval`. They will be labeled **synthetic-reference leave-one-out evaluation**, not learner-population accuracy.

Run the receipt after the validated target corpus is present:

```bash
uv run --project api python -m api.eval
```

The evaluator fits scales, confidence temperature, and abstention inside grouped leave-one-word-out folds. Northern six-way grading turns on only when accuracy is at least 0.80, macro recall at least 0.75, every-tone recall at least 0.60, hỏi/ngã mutual confusion at most 0.20, and every tone has at least three held-out words. Southern remains four-family scoring while all six curves stay visible.

### Confusion matrix

Pending the validated Stage 0 corpus. No synthetic or hand-entered score is presented as a result.

### DSP versus audio-model benchmark

| Evaluator | Exact-tone accuracy | Acoustic-family accuracy | Receipt |
| --- | ---: | ---: | --- |
| DSP template classifier | Pending | Pending | `api/data/evaluation.json` |
| `gpt-realtime-2.1` audio benchmark | Pending | Pending | `api/data/benchmark_llm.json` |

## License

Dấu is released under the [MIT License](LICENSE). Be Vietnam Pro will be self-hosted under its SIL Open Font License, included beside the font files.
