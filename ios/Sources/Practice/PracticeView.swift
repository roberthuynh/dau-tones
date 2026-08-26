import AVFoundation
import DauCore
import SwiftUI

/// Screens 03 and 04 — the loop. Trace live while you speak, judge the moment you stop.
///
/// A thin wrapper so the session below can hold a non-optional word. An empty set is not a
/// runnable state — it crashed here once — and it is cheaper to refuse it at the door than to
/// thread an optional through every subview.
struct PracticeView: View {
    let words: [DauContent.Word]
    var onFinished: () -> Void = {}
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        if words.isEmpty {
            Color.clear.onAppear { dismiss() }
        } else {
            PracticeSessionView(words: words, onFinished: onFinished)
        }
    }
}

private struct PracticeSessionView: View {
    let words: [DauContent.Word]
    var onFinished: () -> Void = {}

    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @Environment(ProgressStore.self) private var progress
    @Environment(\.dismiss) private var dismiss

    @State private var analyzer = LiveToneAnalyzer()
    @State private var index = 0
    @State private var verdict: ToneVerdict?
    @State private var micDenied = false

    /// Safe by construction: the wrapper refuses an empty set, and the index is clamped so a
    /// stale value can never run off the end.
    private var word: DauContent.Word { words[min(max(index, 0), words.count - 1)] }

    private var reference: [Double]? {
        store.referenceContour(word: word.id, accent: settings.accent)
    }

    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                if let verdict {
                    VerdictView(
                        verdict: verdict,
                        word: word,
                        learner: analyzer.drawnContour,
                        reference: reference,
                        onRetry: { retry() },
                        onNext: { advance() }
                    )
                } else {
                    recordingBody
                }
            }
            .padding(.horizontal, 24)
            .padding(.top, 14)
        }
        .onDisappear { analyzer.cancel() }
    }

    // MARK: - Recording

    private var recordingBody: some View {
        VStack(spacing: 0) {
            wordHeader.padding(.top, 22)
            traceCard.padding(.top, 18)
            Text(VerdictCopy.physicalCue(for: word.tone))
                .font(.system(size: 15))
                .foregroundStyle(DauTheme.muted)
                .multilineTextAlignment(.center)
                .padding(.top, 22)
            Spacer()
            recordButton
            Text(recordHint)
                .font(.system(size: 13))
                .foregroundStyle(DauTheme.faint)
                .padding(.top, 14)
                .padding(.bottom, 30)
        }
    }

    private var wordHeader: some View {
        HStack(spacing: 14) {
            ToneContourGlyph(tone: word.tone.glyphMark(for: settings.accent), width: 34)
                .frame(width: 56, height: 56)
                .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 16))
                .overlay(RoundedRectangle(cornerRadius: 16).stroke(DauTheme.hairline, lineWidth: 1))
            VStack(alignment: .leading, spacing: 2) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(word.syllable)
                        .font(.system(size: 46, weight: .bold))
                        .foregroundStyle(DauTheme.toneColor(word.tone))
                    Text(word.meaningEn)
                        .font(.system(size: 15))
                        .foregroundStyle(DauTheme.muted)
                }
                Text("dấu \(word.tone.label) · \(word.tone.hint)")
                    .font(.system(size: 12.5))
                    .textCase(.uppercase)
                    .tracking(1.2)
                    .foregroundStyle(DauTheme.faint)
            }
            Spacer()
            if store.referenceAudioURL(word: word.id, accent: settings.accent) != nil {
                Button { ReferencePlayer.shared.play(url: store.referenceAudioURL(word: word.id, accent: settings.accent)!) } label: {
                    Image(systemName: "speaker.wave.2.fill")
                        .foregroundStyle(Color(hex: 0xCDC4B4))
                        .frame(width: 44, height: 44)
                        .background(DauTheme.card, in: Circle())
                }
                .accessibilityLabel("Hear the \(settings.accent.label) target")
            }
        }
        .accessibilityIdentifier("practiceWord")
    }

    private var traceCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(reference == nil ? "YOUR PITCH" : "FOLLOW THE GLOWING LINE")
                    .font(.system(size: 11.5, weight: .bold))
                    .tracking(1.4)
                    .foregroundStyle(DauTheme.faint)
                Spacer()
                if analyzer.isRecording {
                    HStack(spacing: 6) {
                        Circle().fill(DauTheme.verified).frame(width: 7, height: 7)
                        Text(analyzer.isBaselineSettled ? "Listening…" : "Finding your pitch…")
                            .font(.system(size: 12))
                            .foregroundStyle(DauTheme.verified)
                    }
                }
            }
            ToneCurveView(
                target: reference,
                learner: analyzer.drawnContour,
                // Pinned while live so the target cannot shift under someone tracking it.
                fixedBounds: analyzer.isRecording ? ToneCurveView.bounds(forTarget: reference) : nil,
                isLive: analyzer.isRecording
            )
            .frame(height: 200)
            legend
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 18)
        .background(DauTheme.well, in: RoundedRectangle(cornerRadius: 24))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private var legend: some View {
        HStack(spacing: 14) {
            if reference != nil {
                legendItem(color: DauTheme.coral, label: "\(settings.accent.label) target")
            }
            legendItem(color: DauTheme.cream, label: "You")
            Spacer()
        }
        .padding(.top, 2)
    }

    private func legendItem(color: Color, label: String) -> some View {
        HStack(spacing: 6) {
            Capsule().fill(color).frame(width: 16, height: 3)
            Text(label).font(.system(size: 12)).foregroundStyle(DauTheme.faint)
        }
    }

    private var recordButton: some View {
        Button {
            analyzer.isRecording ? finishTake() : beginTake()
        } label: {
            ZStack {
                if analyzer.isRecording {
                    Circle().fill(DauTheme.coral.opacity(0.35))
                        .frame(width: 120, height: 120)
                        .blur(radius: 8)
                }
                Circle().fill(DauTheme.coral)
                    .frame(width: 96, height: 96)
                    .shadow(color: DauTheme.coral.opacity(0.35), radius: 20, y: 10)
                if analyzer.isRecording {
                    RoundedRectangle(cornerRadius: 8).fill(DauTheme.onCoral).frame(width: 30, height: 30)
                } else {
                    Image(systemName: "mic.fill").font(.system(size: 34)).foregroundStyle(DauTheme.onCoral)
                }
            }
            // Thumb-zone target, comfortably past the 88pt the design asks for.
            .frame(width: 120, height: 120)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("recordButton")
        .accessibilityLabel(analyzer.isRecording ? "Stop recording" : "Record \(word.syllable)")
    }

    private var recordHint: String {
        if let failure = analyzer.failure { return failure }
        if micDenied { return "Microphone access is off. Turn it on in Settings to practice." }
        return analyzer.isRecording ? "Recording — tap to stop" : "Tap and say \(word.syllable)"
    }

    private var topBar: some View {
        HStack {
            Button { dismiss() } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(DauTheme.faint)
                    .frame(width: 40, height: 40)
                    .background(DauTheme.card, in: Circle())
            }
            .accessibilityLabel("Close")
            Spacer()
            HStack(spacing: 5) {
                ForEach(words.indices, id: \.self) { position in
                    Capsule()
                        .fill(pipColor(position))
                        .frame(width: 22, height: 5)
                }
            }
            Spacer()
            Text("\(min(index + 1, words.count)) of \(words.count)")
                .font(.system(size: 13))
                .foregroundStyle(DauTheme.faint)
        }
    }

    private func pipColor(_ position: Int) -> Color {
        if position < index { return DauTheme.verified }
        if position == index { return DauTheme.coral }
        return DauTheme.cream.opacity(0.15)
    }

    // MARK: - Actions

    private func beginTake() {
        // A bundled fixture needs no microphone, so it must not trigger the permission
        // sheet — doing so blocks the whole deterministic test path on a system dialog.
        guard TakeSource.current == .microphone else {
            verdict = nil
            analyzer.start()
            finishTake()
            return
        }
        Task {
            if DauAudioSession.shared.permission == .undetermined {
                _ = await DauAudioSession.shared.requestPermission()
            }
            guard DauAudioSession.shared.permission != .denied else {
                micDenied = true
                return
            }
            verdict = nil
            analyzer.start()
        }
    }

    private func finishTake() {
        let take = analyzer.stop()
        let judged = VerdictPolicy.judge(
            target: word.tone,
            accent: settings.accent,
            features: take?.takeFeatures,
            referenceContour: reference,
            learnerContour: take?.filledContour
        )
        verdict = judged
        progress.record(verdict: judged, wordID: word.id)
    }

    private func retry() {
        verdict = nil
        analyzer.cancel()
    }

    private func advance() {
        verdict = nil
        analyzer.cancel()
        if index + 1 < words.count {
            index += 1
        } else {
            progress.completeToday()
            onFinished()
            dismiss()
        }
    }
}

/// Plays a bundled reference through the shared session.
@MainActor
final class ReferencePlayer {
    static let shared = ReferencePlayer()
    private var player: AVAudioPlayer?

    func play(url: URL) {
        DauAudioSession.shared.activate(.referencePlayback)
        player = try? AVAudioPlayer(contentsOf: url)
        player?.play()
    }
}
