import DauCore
import SwiftUI

/// Screen 02's map, promoted to its own tab: one sound, six meanings, then everything else.
struct WordsView: View {
    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @State private var selected: DauContent.Word?

    private var otherWords: [DauContent.Word] {
        let six = Set(store.sixMaWords.map(\.id))
        return store.featuredWords.filter { !six.contains($0.id) }
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    maGrid
                    otherSection
                }
                .padding(20)
            }
            .background(DauTheme.ground)
            .navigationTitle("Words")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(DauTheme.ground, for: .navigationBar)
        }
        .sheet(item: $selected) { word in
            WordDetailSheet(word: word)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("One sound. Six meanings.")
                .font(.system(size: 27, weight: .bold))
                .foregroundStyle(DauTheme.cream)
            Text("Your pitch decides which word you said.")
                .font(.subheadline)
                .foregroundStyle(DauTheme.muted)
        }
    }

    private var maGrid: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
            ForEach(store.sixMaWords) { word in
                Button { selected = word } label: { WordCard(word: word) }
                    .buttonStyle(.plain)
            }
        }
        .accessibilityIdentifier("maGrid")
    }

    private var otherSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("More words")
                .font(.caption.bold())
                .tracking(1.4)
                .foregroundStyle(DauTheme.faint)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(otherWords) { word in
                    Button { selected = word } label: { WordCard(word: word) }
                        .buttonStyle(.plain)
                }
            }
        }
    }
}

struct WordCard: View {
    let word: DauContent.Word
    @Environment(DauSettings.self) private var settings

    var body: some View {
        VStack(spacing: 6) {
            ToneContourGlyph(tone: word.tone.glyphMark(for: settings.accent), width: 34)
                .frame(height: 20)
            Text(word.syllable)
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(DauTheme.cream)
            Text(word.meaningEn)
                .font(.system(size: 11.5))
                .foregroundStyle(DauTheme.faint)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(
            RoundedRectangle(cornerRadius: 18).stroke(DauTheme.hairline, lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(word.syllable), \(word.meaningEn), tone \(word.tone.label)")
    }
}

struct WordDetailSheet: View {
    let word: DauContent.Word
    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(word.syllable)
                            .font(.system(size: 46, weight: .bold))
                            .foregroundStyle(DauTheme.toneColor(word.tone))
                        VStack(alignment: .leading) {
                            Text(word.meaningEn).font(.title3).foregroundStyle(DauTheme.cream)
                            Text("dấu \(word.tone.label) · \(word.tone.hint)")
                                .font(.caption)
                                .textCase(.uppercase)
                                .tracking(1.2)
                                .foregroundStyle(DauTheme.faint)
                        }
                    }
                    if !word.usageNote.isEmpty {
                        Text(word.usageNote)
                            .font(.subheadline)
                            .foregroundStyle(DauTheme.muted)
                    }
                    if let cue = store.content.tone(word.tone)?.physicalCue, !cue.isEmpty {
                        Label(cue, systemImage: "figure.stand")
                            .font(.subheadline)
                            .foregroundStyle(DauTheme.cream)
                            .padding(14)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 16))
                    }
                    if !word.hasReference(for: settings.accent) {
                        // Said plainly rather than hidden. The rule verdict is pitch-only and
                        // still works; only the target audio is missing.
                        Text("No \(settings.accent.label) recording of this one yet — you can still practice it, you just won't hear a target.")
                            .font(.footnote)
                            .foregroundStyle(DauTheme.faint)
                    }
                    Spacer(minLength: 8)
                }
                .padding(20)
            }
            .background(DauTheme.ground)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }.foregroundStyle(DauTheme.coral)
                }
            }
        }
        .presentationDetents([.medium])
    }
}
