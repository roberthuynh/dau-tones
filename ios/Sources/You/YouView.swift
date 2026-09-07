import DauCore
import SwiftUI

/// Screen 06 — change made visible, and the privacy claim restated where someone looking for
/// it will find it.
struct YouView: View {
    @Environment(ContentStore.self) private var store
    @Environment(DauSettings.self) private var settings
    @Environment(ProgressStore.self) private var progress
    @Environment(QuestProgressStore.self) private var quest

    private var takesGraded: Int { progress.progress.takes.count }
    private var recentPassRate: (passed: Int, total: Int)? {
        let recent = progress.progress.takes.suffix(30)
        guard !recent.isEmpty else { return nil }
        return (recent.filter(\.passed).count, recent.count)
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Your journey")
                        .font(.system(size: 26, weight: .bold))
                        .foregroundStyle(DauTheme.cream)
                    missionProgress
                    statRow
                    byToneCard
                    settingsCard
                    privacyNote
                }
                .padding(20)
            }
            .background(DauTheme.ground)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(DauTheme.ground, for: .navigationBar)
            .onAppear { settings.probeOnDeviceRecognition() }
        }
    }

    private var missionProgress: some View {
        HStack(spacing: 14) {
            Image(systemName: quest.isCompleted ? "checkmark.seal.fill" : "map.fill")
                .font(.system(size: 24))
                .foregroundStyle(quest.isCompleted ? DauTheme.jade : DauTheme.coral)
                .frame(width: 48, height: 48)
                .background((quest.isCompleted ? DauTheme.jade : DauTheme.coral).opacity(0.11), in: RoundedRectangle(cornerRadius: 15))
            VStack(alignment: .leading, spacing: 3) {
                Text(quest.isCompleted ? "Café mission completed" : "Café mission in progress")
                    .font(.system(size: 16, weight: .bold, design: .rounded)).foregroundStyle(DauTheme.ink)
                Text(quest.isCompleted ? "A short revisit will appear when it’s due." : "Your place is saved on this iPhone.")
                    .font(.system(size: 13, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(DauTheme.hairline))
    }

    private var statRow: some View {
        HStack(spacing: 8) {
            statTile(
                value: "\(progress.progress.currentStreak)",
                label: "day streak",
                tint: Color(hex: 0x966015)
            )
            statTile(value: "\(takesGraded)", label: "takes graded", tint: DauTheme.cream)
            statTile(
                value: recentPassRate.map { "\($0.passed)/\($0.total)" } ?? "—",
                label: "last 30",
                tint: DauTheme.verified
            )
        }
    }

    private func statTile(value: String, label: String, tint: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(value).font(.system(size: 23, weight: .bold)).foregroundStyle(tint)
            Text(label).font(.system(size: 11.5)).foregroundStyle(DauTheme.faint)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 14)
        .padding(.vertical, 13)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private var byToneCard: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("BY TONE")
                .font(.system(size: 11.5, weight: .bold))
                .tracking(1.4)
                .foregroundStyle(DauTheme.faint)
            HStack(alignment: .bottom, spacing: 10) {
                ForEach(ToneMark.allCases, id: \.self) { tone in
                    toneBar(tone)
                }
            }
            .frame(height: 84)
            Text(weakestPairNote)
                .font(.system(size: 12.5))
                .foregroundStyle(DauTheme.faint)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(18)
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private func toneBar(_ tone: ToneMark) -> some View {
        let mastery = progress.mastery(forTone: tone)
        let fraction = mastery.map { $0.total > 0 ? Double($0.passed) / Double($0.total) : 0 } ?? 0
        return VStack(spacing: 5) {
            Spacer(minLength: 0)
            RoundedRectangle(cornerRadius: 8)
                .fill(DauTheme.toneColor(tone))
                .frame(height: max(4, 62 * fraction))
                .opacity(mastery == nil ? 0.25 : 1)
            Text(tone.label)
                .font(.system(size: 11))
                .foregroundStyle(DauTheme.faint)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(
            mastery.map { "\(tone.label): \($0.passed) of your last \($0.total) takes" }
                ?? "\(tone.label): not practised yet"
        )
    }

    private var weakestPairNote: String {
        let practised = ToneMark.allCases.filter { progress.mastery(forTone: $0) != nil }
        guard practised.count >= 2 else {
            return "Practise a few more takes and your weakest tones will show up here."
        }
        let weakest = progress.weakestTones().filter { practised.contains($0) }.prefix(2)
        return "\(weakest.map(\.label).joined(separator: " and ")) are your hardest pair — tomorrow's set leans on them."
    }

    private var settingsCard: some View {
        VStack(spacing: 0) {
            settingsRow("Accent", value: "\(settings.accent.label) — \(settings.accent.city)") {
                settings.accent = settings.accent == .north ? .south : .north
            }
            Divider().overlay(DauTheme.hairline)
            settingsRow(
                "Vietnamese dictation",
                value: settings.supportsOnDeviceVietnamese ? "On-device" : "Not installed",
                action: nil
            )
            Divider().overlay(DauTheme.hairline)
            settingsRow("Privacy", value: "On-device grading", action: nil)
        }
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 22))
        .overlay(RoundedRectangle(cornerRadius: 22).stroke(DauTheme.hairline, lineWidth: 1))
    }

    private func settingsRow(_ title: String, value: String, action: (() -> Void)?) -> some View {
        Button { action?() } label: {
            HStack {
                Text(title).font(.system(size: 15, weight: .bold)).foregroundStyle(DauTheme.cream)
                Spacer()
                Text(value)
                    .font(.system(size: 14))
                    .foregroundStyle(action == nil ? DauTheme.verified : DauTheme.faint)
                if action != nil {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(DauTheme.faint)
                }
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 52)
        }
        .buttonStyle(.plain)
        .disabled(action == nil)
    }

    private var privacyNote: some View {
        // Restated where someone who cares will go looking, in the same words as the claim on
        // first run. The app has no network client; this is a description, not a promise.
        Text("Mission recordings and tone takes stay on this iPhone and are never uploaded. VietQuest has no account, no analytics, and makes no network requests — it works with the radio off.")
            .font(.system(size: 12.5))
            .foregroundStyle(DauTheme.faint)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 4)
    }
}
