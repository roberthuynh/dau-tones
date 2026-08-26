import DauCore
import SwiftUI

/// Screen 05 — say a whole phrase, see each word settle with the tone you actually gave it.
///
/// This is the prompted mode, and it uses **no speech recognition at all**: the words are
/// already known, so the syllable segmenter supplies the timing and the rule table supplies
/// each verdict. That means it works on every device, needs no extra permission, and keeps
/// the privacy claim intact. Free-speech mode is the same screen with recognition supplying
/// word identity — and even then, the tone shown always comes from the DSP.
struct CaptionsView: View {
    let phrase: Phrase

    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss

    @State private var analyzer = LiveToneAnalyzer()
    @State private var words: [CaptionWord] = []
    @State private var shortfall: String?
    @State private var hasTake = false
    @State private var laneContour: [Double] = []

    private var syllables: [PhraseSyllable] { phrase.syllables }

    var body: some View {
        ZStack {
            DauTheme.ground.ignoresSafeArea()
            VStack(spacing: 0) {
                topBar
                prompt.padding(.top, 16)
                captionCard.padding(.top, 14)
                if let shortfall {
                    Text(shortfall)
                        .font(.system(size: 12.5))
                        .foregroundStyle(DauTheme.faint)
                        .padding(.top, 10)
                }
                legend.padding(.top, 12)
                if hasTake { pitchLane.padding(.top, 14) }
                Spacer(minLength: 12)
                recordButton
                Text(analyzer.isRecording ? "Listening — tap to finish" : (hasTake ? "Tap a word to drill it" : "Tap and say the whole line"))
                    .font(.system(size: 13))
                    .foregroundStyle(DauTheme.faint)
                    .padding(.top, 12)
                    .padding(.bottom, 28)
            }
            .padding(.horizontal, 24)
            .padding(.top, 14)
        }
        .onAppear { resetWords() }
        .onDisappear { analyzer.cancel() }
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
            Text("LIVE CAPTIONS")
                .font(.system(size: 12, weight: .bold))
                .tracking(1.6)
                .foregroundStyle(DauTheme.faint)
            Spacer()
            Text(settings.accent.label)
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Color(hex: 0xCDC4B4))
                .padding(.horizontal, 13)
                .padding(.vertical, 8)
                .background(DauTheme.card, in: Capsule())
        }
    }

    private var prompt: some View {
        VStack(spacing: 4) {
            Text("Say this line — each word is graded as you finish it.")
                .font(.system(size: 13))
                .foregroundStyle(DauTheme.faint)
            Text(phrase.gloss)
                .font(.system(size: 13))
                .foregroundStyle(DauTheme.muted)
                .multilineTextAlignment(.center)
        }
    }

    private var captionCard: some View {
        VStack(alignment: .leading, spacing: 20) {
            FlowLayout(spacing: 16, rowSpacing: 20) {
                ForEach(words) { word in
                    captionWord(word)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20)
        .padding(.vertical, 24)
        .background(DauTheme.well, in: RoundedRectangle(cornerRadius: 24))
        .overlay(RoundedRectangle(cornerRadius: 24).stroke(DauTheme.hairline, lineWidth: 1))
        .accessibilityIdentifier("captionCard")
    }

    private func captionWord(_ word: CaptionWord) -> some View {
        VStack(spacing: 4) {
            ToneContourGlyph(
                tone: displayTone(word).glyphMark(for: settings.accent),
                width: 26,
                color: glyphColor(word)
            )
            Text(word.display)
                .font(.system(size: 27, weight: .bold))
                .foregroundStyle(textColor(word))
                .overlay(alignment: .bottom) {
                    if word.isMissed {
                        Rectangle()
                            .fill(DauTheme.missed)
                            .frame(height: 2.5)
                            .offset(y: 4)
                    }
                }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel(word))
    }

    private func displayTone(_ word: CaptionWord) -> ToneMark {
        if case .missed(let produced) = word.state, let produced { return produced }
        return word.expected.tone
    }

    private func glyphColor(_ word: CaptionWord) -> Color {
        switch word.state {
        case .matched: DauTheme.toneColor(word.expected.tone)
        case .missed: DauTheme.missed
        case .unread, .pending: DauTheme.faint.opacity(0.5)
        }
    }

    private func textColor(_ word: CaptionWord) -> Color {
        switch word.state {
        case .matched: DauTheme.cream
        case .missed: Color(hex: 0xFF8A7A)
        case .unread: DauTheme.faint
        case .pending: Color(hex: 0xCDC4B4).opacity(0.55)
        }
    }

    private func accessibilityLabel(_ word: CaptionWord) -> String {
        switch word.state {
        case .matched: "\(word.display), matched"
        case .missed: "\(word.expected.surface) came out as \(word.display)"
        case .unread: "\(word.display), not read clearly"
        case .pending: "\(word.display), not reached"
        }
    }

    private var legend: some View {
        HStack(spacing: 14) {
            legendDot(DauTheme.cream, "matched")
            legendDot(DauTheme.missed, "didn't match")
            legendDot(DauTheme.faint.opacity(0.6), "not read")
            Spacer()
        }
    }

    private func legendDot(_ color: Color, _ label: String) -> some View {
        HStack(spacing: 6) {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(label).font(.system(size: 12)).foregroundStyle(DauTheme.faint)
        }
    }

    /// The rolling lane from the design: your pitch across the whole phrase, with the
    /// syllable boundaries the segmenter actually found marked on it. Those gridlines are
    /// measured, not decorative — they show where the app decided one word ended.
    private var pitchLane: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("YOUR PITCH ACROSS THE LINE")
                .font(.system(size: 11.5, weight: .bold))
                .tracking(1.4)
                .foregroundStyle(DauTheme.faint)
            ToneCurveView(target: nil, learner: laneContour)
                .frame(height: 96)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 14)
        .background(DauTheme.well, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private var recordButton: some View {
        Button {
            analyzer.isRecording ? finish() : begin()
        } label: {
            ZStack {
                Circle().fill(DauTheme.coral)
                    .frame(width: 84, height: 84)
                    .shadow(color: DauTheme.coral.opacity(0.32), radius: 18, y: 8)
                Image(systemName: analyzer.isRecording ? "stop.fill" : "mic.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(DauTheme.onCoral)
            }
            .frame(width: 110, height: 110)
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("captionRecordButton")
        .accessibilityLabel(analyzer.isRecording ? "Finish" : "Say the line")
    }

    // MARK: - Actions

    private func resetWords() {
        words = syllables.enumerated().map { index, syllable in
            CaptionWord(id: index, expected: syllable, state: .pending, display: syllable.surface)
        }
        shortfall = nil
        hasTake = false
        laneContour = []
    }

    private func begin() {
        guard TakeSource.current == .microphone else {
            resetWords()
            analyzer.start(maximumSeconds: LiveToneAnalyzer.maximumPhraseSeconds)
            finish()
            return
        }
        Task {
            if DauAudioSession.shared.permission == .undetermined {
                _ = await DauAudioSession.shared.requestPermission()
            }
            guard DauAudioSession.shared.permission != .denied else { return }
            resetWords()
            analyzer.start(maximumSeconds: LiveToneAnalyzer.maximumPhraseSeconds)
        }
    }

    private func finish() {
        guard let take = analyzer.stop() else { return }
        hasTake = true
        // Segmentation runs on the raw 10 ms frames, never the resampled display contour —
        // resampling destroys exactly the gap structure that separates syllables.
        let reading = PhraseToneReader.read(contour: take.frames, maximumSyllables: syllables.count)
        let slices = reading.map { current in
            current.syllableRanges.map { range in
                Array(take.frames[range])
            }
        } ?? []

        words = CaptionBuilder.build(
            phrase: syllables, reading: reading, accent: settings.accent,
            features: { index in
                guard index < slices.count,
                      let contour = ToneContourFeatures.of(contour: slices[index]) else { return nil }
                // Per-syllable energy evidence is not separable from one take's envelope, so
                // the neutral block is used here. It only affects nặng and the merged
                // Southern pair, and using a guessed value would be worse than none.
                return ToneTakeFeatures(contour: contour, energy: .neutral)
            }
        )
        shortfall = CaptionBuilder.shortfallNote(words: words)
        laneContour = take.frames.compactMap { $0 }
    }
}

/// Minimal wrapping layout for the caption words.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var rowSpacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > width, x > 0 {
                x = 0
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: width == .infinity ? x : width, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, rowHeight: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > bounds.maxX, x > bounds.minX {
                x = bounds.minX
                y += rowHeight + rowSpacing
                rowHeight = 0
            }
            subview.place(at: CGPoint(x: x, y: y), anchor: .topLeading, proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
