# Dấu — privacy

## The product rule

Dấu analyzes your voice **on this iPhone** and never sends it anywhere. There is no account, no
analytics SDK, and no network client in the app at all. This is not a policy the app tries to
honour — it is a property of the binary, checked by a build gate (`InfraAuditTests`).

The simplest proof: **the whole app works in airplane mode.**

## What is stored, and where

On device only, in `Application Support/dau-progress-v1.json` and `UserDefaults`:

- which words you practised, when, and whether each take passed its tone rule
- the shape-match percentage for a take, and the acoustic feature block behind it
- your accent choice, streak, and reminder preference

That record **must not** contain a name, an email address, a contact, a location, an advertising
identifier, a device fingerprint, free-form text you typed, or any cross-app identifier. Neither
record is ever uploaded.

Recordings are written to the system temporary directory so a take can be replayed ("hear
yours") and are not backed up or transmitted.

## Network behaviour

The app makes no network requests. It contains no analytics, crash-reporting, attribution, ad,
remote-config or support-chat SDK. Speech recognition, where used, is pinned to
`requiresOnDeviceRecognition = true` and never falls back to a server — if a device cannot
recognize Vietnamese locally, the feature degrades to the prompted mode rather than going online.

Do not add any of the above without a separate, approved privacy review and an explicit scope
change.

## App Store privacy label

**Data Not Collected.** Verify before every submission:

1. Inspect linked frameworks and the generated privacy manifest report.
2. Confirm no third-party SDK arrived via SPM or a binary framework.
3. Exercise every flow with a network inspector attached and confirm no requests.
4. **Confirm full functionality in airplane mode** — for this app that is the product claim.
5. Reconcile the App Store Connect privacy answers against the shipping binary.

## Microphone

`NSMicrophoneUsageDescription` states the boundary inside the permission prompt itself, because
that is the moment someone decides. Recording begins only on an explicit tap and stops on the
next tap or at the take limit.
