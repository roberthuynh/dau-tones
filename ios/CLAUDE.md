# Dấu iOS — agent instructions

SwiftUI tone trainer. Plan of record: `~/.claude/plans/i-just-downloaded-a-majestic-shamir.md`.

## Non-negotiables

- **Nothing under `~/Projects/Personal/hackathon/` is ever written to.** That checkout is the
  award-time record. This repo (`ninth-tile/dau-tones`) is the working copy for everything,
  web and iOS alike.
- **The 72%-accurate template classifier stays out.** No DTW, no `ToneTemplate`, no softmax
  "class confidence" — nghe deliberately declined to port it and so do we. Verdicts come from
  the per-target rule table plus the family judge. If DTW templates ever land in the repo,
  someone will wire them up.
- **Any number shown is a measurement, never a model's opinion.** A `%` may only be a
  *shape match* against a known target, or an observed tally ("8 of your last 10"). Suppress
  it entirely on weak signal rather than softening it.
- **Nothing phones home.** No analytics SDK, no network client. `requiresOnDeviceRecognition`
  is always `true`. The app must work in airplane mode — that *is* the product claim, and
  `InfraAuditTest` fails the build if it stops being true.
- **Seam rule:** nothing in `Sources/` (the app) names a tone, a family, a verdict string, or
  a number format. That all lives in `DauCore/Verdict/`, so honesty constraints stay
  unit-testable without a simulator.

## Simulator

Use the dedicated **`dau-sim`** device, never the shared generic "iPhone 17 Pro":

```sh
xcodebuild -project Dau.xcodeproj -scheme Dau -destination 'platform=iOS Simulator,name=dau-sim' \
  -derivedDataPath build/dd test
```

Several sessions run simulators on this machine at once. Sharing a generic device is how a UI
suite dies with `Test crashed with signal kill` and no assertion — another session drove your
device mid-test. A dedicated name costs nothing and removes the whole failure class.

Build to an explicit `-derivedDataPath` and install *that* product before any screenshot. Never
glob DerivedData: Xcode keeps one directory per configuration hash, so `head -1` is not "latest"
and a stale build silently no-ops launch arguments like `-uiTestTakeFixture`.

## Engine provenance

`DauCore` is ported from Robert's own code — nghe's `NgheCore/ToneLab` (rule-based judge,
speaker-relative contours) and the Python in `../api/dau/tones.py` (per-target rule table,
family map, RMS features). Copy, don't cross-link; that's the fleet convention.

Two audio-session behaviors are carried verbatim from nghe because they were paid for in bugs:
capture never enables `.allowBluetoothHFP` (an 8 kHz HFP mic starves the RMS gate), and a live
take wins the session. Do not "simplify" either.

## Reference contours

Shipped reference contours are **recomputed with the Swift analyzer** at build time. The
Python-derived contours in `../targets/generation-report.json` are test fixtures only — drawing
a librosa target line against a Swift learner line reads estimator disagreement as learner
error, and now also feeds the shape-match number.
