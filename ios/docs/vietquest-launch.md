# VietQuest initial course release

Approved direction: extend this native app in the Ninth Tile repository; Southern-first,
English-speaking adult beginners and heritage learners, with a polished first café mission.
The legacy hackathon checkout is immutable. The bundle identity remains unchanged to preserve
Nook TestFlight distribution and installed progress.

## Learning contract

Teach coffee/water requests, a contextual cô/con relationship, repetition, unavailable coffee,
switching to water, and confirmation. Preparation can be skipped without awarding mastery.
Supported and independent meaning choices are distinct; local recordings are practice, not
automatic evidence of intelligibility. Review is available after the lesson and becomes due
the following day. Existing tone feedback stays accessible as a focused practice tool.

## Assets

Eight complete authored café utterances are bundled under Content/quest/audio, C01 through C08.
Four are hash-verified Nghe OpenAI recordings. Four were generated in a bounded four-request
batch with the same existing voice profiles. No video sentence slices or stitched models are used.
Provenance and exact text live in art/Generation/vietquest-v1. Returned transcript validation is
not native-speaker editorial approval; any independent listening review must be reported separately.

The café hero and speech-map icon use Codex built-in image generation. Original bytes, full
prompts, hashes, and deterministic packaging are preserved in the same provenance directory.

## Release boundary

The public-name check found EZViet already uses VietQuest for a Vietnamese-learning game:
https://ezviet.org/. Robert explicitly approved retaining VietQuest for this release.
Public marketing and name clearance remain separate from implementation.

Nghe Class, the family recording companion, an admin console, cloud tutoring, accounts,
telemetry, paywalls, and the remaining eleven planned missions are outside this initial release.
The untracked earlier docs/plans files predate this implementation and are not silently included
in the release commit.

## Acceptance gates

Core tests, app persistence tests, complete café UI flow, denied microphone and quiet practice,
resume/review, reference/recording exclusivity, bounded temporary recording, background cleanup,
asset hashes/decoding, Dynamic Type and reduced-motion visual review, then signed Release
archive and Nook TestFlight processing/installability. Evidence is recorded as checks actually run;
this checklist alone does not assert completion.

## Verification receipt, 2026-09-07

- `swift test --package-path ios/DauCore`: passed 10 XCTest tests and 59 Swift Testing tests.
- `xcodebuild -project ios/Dau.xcodeproj -scheme Dau -destination 'platform=iOS Simulator,name=dau-sim' -derivedDataPath ios/build/dd -parallel-testing-enabled NO test`: passed 15 app tests and 9 UI tests.
- `python3 ios/tools/validate-quest-assets.py`: passed transcript, provenance/hash, image and audio decoding checks.
- `npm run typecheck`: passed.
- `git diff --check`: passed.
- Final simulator onboarding and mission-completion screenshots were visually inspected: illustration renders, text is readable, and controls fit the captured viewport.

The UI accessibility audit excludes one exact listening-instruction paragraph from contrast checking. Saved pixel evidence in `contrast-receipt.json` and `contrast-evidence.png` measures 18.68:1; other contrast and text-clipping checks remain enforced.

These results do not establish native-speaker audio approval, physical-device microphone behavior, signed Release archive success, or TestFlight availability. Those release checks remain outstanding. The naming decision is resolved: retain VietQuest. No TestFlight upload has occurred yet.
