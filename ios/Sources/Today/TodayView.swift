import DauCore
import SwiftUI

/// Screen 02 — the daily ritual. Three words, a streak, and the ma map as the progress
/// display rather than a stats dashboard.
struct TodayView: View {
    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @Environment(ProgressStore.self) private var progress
    /// The running session, if any.
    ///
    /// Presented by item rather than by a boolean plus a separate array: the words must
    /// arrive with the presentation, atomically. Two `@State` writes in one action are not
    /// guaranteed to be visible to the cover in the same pass, and an empty word list is a
    /// crash. The snapshot also matters on its own — `todaysThree` is derived from the
    /// learner's weakest tones, so recording a take reorders it, and a set that reshuffles
    /// itself mid-session pulls the screen out from under you.
    @State private var session: PracticeSession?

    /// Today's three, picked from the learner's weakest tones and stable for the day.
    ///
    /// Seeded by the day key so the set does not reshuffle when the view redraws — the same
    /// day always offers the same three words.
    private var todaysThree: [DauContent.Word] {
        let pool = store.featuredWords
        var chosen: [DauContent.Word] = []
        var takenIDs: Set<String> = []

        // Weakest tones first — tomorrow's set leans on what today went worst.
        for tone in progress.weakestTones() {
            guard chosen.count < 3 else { break }
            if let word = pool.first(where: { $0.tone == tone && !takenIDs.contains($0.id) }) {
                chosen.append(word)
                takenIDs.insert(word.id)
            }
        }
        for word in pool where chosen.count < 3 && !takenIDs.contains(word.id) {
            chosen.append(word)
            takenIDs.insert(word.id)
        }
        return chosen
    }

    private var completedCount: Int {
        let ids = Set(todaysThree.map(\.id))
        return Set(progress.takesToday.filter { ids.contains($0.wordID) && $0.passed }.map(\.wordID)).count
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    greeting
                    todayCard
                    maMap
                }
                .padding(20)
            }
            .background(DauTheme.ground)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(DauTheme.ground, for: .navigationBar)
        }
        .fullScreenCover(item: $session) { session in
            PracticeView(words: session.words)
        }
    }

    private var greeting: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text(timeOfDay)
                    .font(.system(size: 13))
                    .foregroundStyle(DauTheme.faint)
                Text("Chào bạn")
                    .font(.system(size: 26, weight: .bold))
                    .foregroundStyle(DauTheme.cream)
            }
            Spacer()
            if progress.progress.currentStreak > 0 {
                HStack(spacing: 7) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(Color(hex: 0xF4A641))
                        .frame(width: 9, height: 9)
                        .rotationEffect(.degrees(45))
                    Text("\(progress.progress.currentStreak)")
                        .font(.system(size: 14, weight: .bold))
                        .foregroundStyle(Color(hex: 0xF4A641))
                    Text("day streak")
                        .font(.system(size: 12))
                        .foregroundStyle(DauTheme.muted)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 9)
                .background(DauTheme.card, in: Capsule())
                .overlay(Capsule().stroke(Color(hex: 0xF4A641).opacity(0.35), lineWidth: 1))
            }
        }
    }

    private var timeOfDay: String {
        let hour = Calendar.current.component(.hour, from: progress.now)
        switch hour {
        case 5..<12: return "Morning"
        case 12..<17: return "Afternoon"
        default: return "Evening"
        }
    }

    private var todayCard: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("TODAY'S THREE")
                    .font(.system(size: 12, weight: .bold))
                    .tracking(1.6)
                    .foregroundStyle(DauTheme.faint)
                Spacer()
                Text("\(completedCount) of 3 done")
                    .font(.system(size: 12.5))
                    .foregroundStyle(DauTheme.faint)
            }
            HStack(spacing: 8) {
                ForEach(Array(todaysThree.enumerated()), id: \.element.id) { position, word in
                    todayChip(word, position: position)
                }
            }
            Button {
                let words = todaysThree
                guard !words.isEmpty else { return }
                session = PracticeSession(words: words)
            } label: {
                Text(completedCount >= 3 ? "Practice again" : "Continue · 2 min")
                    .font(.system(size: 16, weight: .bold))
                    .foregroundStyle(DauTheme.onCoral)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(DauTheme.coral, in: Capsule())
            }
            .accessibilityIdentifier("continueButton")
        }
        .padding(18)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private func todayChip(_ word: DauContent.Word, position: Int) -> some View {
        let done = progress.takesToday.contains { $0.wordID == word.id && $0.passed }
        let isNext = !done && position == completedCount
        return VStack(spacing: 2) {
            Text(word.syllable)
                .font(.system(size: 21, weight: .bold))
                .foregroundStyle(done ? DauTheme.verified : DauTheme.cream)
            Text(done ? "\(word.meaningEn) · done" : (isNext ? "up next" : word.meaningEn))
                .font(.system(size: 11.5))
                .foregroundStyle(DauTheme.faint)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .background(
            done ? DauTheme.verified.opacity(0.1) : (isNext ? DauTheme.coral.opacity(0.12) : Color(hex: 0x221E17)),
            in: RoundedRectangle(cornerRadius: 16)
        )
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(
            done ? DauTheme.verified.opacity(0.4) : (isNext ? DauTheme.coral : DauTheme.hairline),
            lineWidth: isNext ? 1.5 : 1
        ))
    }

    /// "ghost · 8/10" — a count of what actually happened, not a percentage that implies a
    /// model's opinion. Words with no history just show their meaning.
    private func masteryLabel(for word: DauContent.Word, mastery: (passed: Int, total: Int)?) -> String {
        guard let mastery, mastery.total > 0 else { return word.meaningEn }
        return "\(word.meaningEn) · \(mastery.passed)/\(mastery.total)"
    }

    private var maMap: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("THE MA MAP")
                .font(.system(size: 12, weight: .bold))
                .tracking(1.6)
                .foregroundStyle(DauTheme.faint)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                ForEach(store.sixMaWords) { word in
                    maCell(word)
                }
            }
        }
    }

    private func maCell(_ word: DauContent.Word) -> some View {
        let mastery = progress.mastery(forWord: word.id)
        return VStack(spacing: 2) {
            HStack {
                Spacer()
                MasteryRing(mastery: mastery, color: DauTheme.toneColor(word.tone))
            }
            Text(word.syllable)
                .font(.system(size: 24, weight: .bold))
                .foregroundStyle(DauTheme.cream)
            // An observed tally, said as one — never a score.
            Text(masteryLabel(for: word, mastery: mastery))
                .font(.system(size: 11.5))
                .foregroundStyle(DauTheme.faint)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .padding(.horizontal, 6)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(DauTheme.hairline, lineWidth: 1))
    }
}

/// One practice run through a fixed set of words.
struct PracticeSession: Identifiable {
    let id = UUID()
    let words: [DauContent.Word]
}

struct MasteryRing: View {
    let mastery: (passed: Int, total: Int)?
    let color: Color

    var body: some View {
        ZStack {
            Circle().stroke(DauTheme.cream.opacity(0.12), lineWidth: 4)
            if let mastery, mastery.total > 0 {
                Circle()
                    .trim(from: 0, to: CGFloat(mastery.passed) / CGFloat(mastery.total))
                    .stroke(color, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
            }
        }
        .frame(width: 20, height: 20)
        .accessibilityHidden(true)
    }
}
