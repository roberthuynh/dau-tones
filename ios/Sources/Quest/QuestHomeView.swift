import SwiftUI

struct QuestHomeView: View {
    @Environment(QuestProgressStore.self) private var quest
    @State private var lessonStep: CafeLessonStep?
    @State private var opensReview = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    header
                    missionCard
                    if quest.isCompleted { reviewCard }
                    nextMissions
                }
                .padding(.horizontal, 20)
                .padding(.top, 12)
                .padding(.bottom, 28)
            }
            .background(DauTheme.ground.ignoresSafeArea())
            .navigationTitle("Today")
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(DauTheme.ground, for: .navigationBar)
        }
        .fullScreenCover(item: $lessonStep) { step in
            CafeLessonView(initialStep: step, isReview: opensReview)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text("CHÀO BẠN")
                .font(.system(.caption, design: .rounded).weight(.bold))
                .tracking(1.8)
                .foregroundStyle(DauTheme.jade)
            Text(quest.isCompleted ? "A little Vietnamese, often." : "Let’s order something good.")
                .font(.system(.largeTitle, design: .rounded).weight(.bold))
                .foregroundStyle(DauTheme.ink)
        }
    }

    private var missionCard: some View {
        VStack(alignment: .leading, spacing: 0) {
            cafeArtwork
                .frame(height: 184)
                .clipped()
                .overlay(alignment: .topLeading) {
                    Text(quest.isCompleted ? "COMPLETED" : "MISSION 1")
                        .questEyebrow(color: quest.isCompleted ? DauTheme.jade : DauTheme.coral)
                        .padding(16)
                }
            VStack(alignment: .leading, spacing: 12) {
                Text("At the café")
                    .font(.system(.title, design: .rounded).weight(.bold))
                    .foregroundStyle(DauTheme.ink)
                Text("Order a drink, hear when it’s unavailable, and choose another.")
                    .font(.system(.body, design: .rounded))
                    .foregroundStyle(DauTheme.inkSoft)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 14) {
                    Label("8–12 min", systemImage: "clock")
                    Label("Southern", systemImage: "waveform")
                }
                .font(.system(.footnote, design: .rounded).weight(.semibold))
                .foregroundStyle(DauTheme.inkSoft)
                Button(action: openMission) {
                    HStack {
                        Text(primaryTitle)
                        Spacer()
                        Image(systemName: "arrow.right")
                    }
                    .questPrimaryButton()
                }
                .accessibilityIdentifier("continueButton")
            }
            .padding(20)
        }
        .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 26))
        .clipShape(RoundedRectangle(cornerRadius: 26))
        .overlay(RoundedRectangle(cornerRadius: 26).stroke(DauTheme.hairline, lineWidth: 1))
        .shadow(color: DauTheme.ink.opacity(0.07), radius: 20, y: 8)
    }

    @ViewBuilder private var cafeArtwork: some View {
        if UIImage(named: "cafe-scene") != nil {
            Image("cafe-scene").resizable().scaledToFill()
        } else {
            ZStack {
                LinearGradient(colors: [DauTheme.jade.opacity(0.9), DauTheme.jadeDark], startPoint: .topLeading, endPoint: .bottomTrailing)
                HStack(alignment: .bottom, spacing: 24) {
                    Image(systemName: "cup.and.saucer.fill").font(.system(size: 68)).foregroundStyle(DauTheme.cream)
                    Image(systemName: "leaf.fill").font(.system(size: 54)).foregroundStyle(DauTheme.coral.opacity(0.9))
                }
            }
        }
    }

    private var primaryTitle: String {
        if quest.isCompleted && !quest.hasActiveRun { return "Practice again" }
        return quest.isStarted ? "Continue mission" : "Start mission"
    }

    private func openMission() {
        opensReview = false
        if quest.isCompleted && !quest.hasActiveRun { quest.restartCafe(); lessonStep = .welcome }
        else { lessonStep = CafeLessonStep(rawValue: min(quest.snapshot.cafeStep, CafeLessonStep.allCases.count - 1)) ?? .welcome }
    }

    private var reviewCard: some View {
        Button { opensReview = true; lessonStep = .listen } label: {
            HStack(spacing: 14) {
                Image(systemName: quest.hasReviewDue ? "bell.badge.fill" : "calendar.badge.clock")
                    .font(.system(.title2))
                    .foregroundStyle(DauTheme.coral)
                    .frame(width: 46, height: 46)
                    .background(DauTheme.coral.opacity(0.12), in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(quest.hasReviewDue ? "Your café revisit is ready" : (quest.snapshot.reviewCount == 0 ? "Revisit tomorrow" : "Your next café revisit"))
                        .font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
                    Text(quest.snapshot.reviewDueAt.map { "Due " + $0.formatted(date: .abbreviated, time: .omitted) } ?? "Hear a familiar request with less help.")
                        .font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
                }
                Spacer()
                Image(systemName: "chevron.right").foregroundStyle(DauTheme.jade)
            }
            .padding(16)
            .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        }
        .buttonStyle(.plain)
    }

    private var nextMissions: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("COMING UP").questSectionTitle()
            HStack(spacing: 10) {
                preview("Meet someone", icon: "person.2.fill")
                preview("The right order", icon: "list.number")
            }
        }
    }

    private func preview(_ title: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            Image(systemName: icon).font(.system(.title2)).foregroundStyle(DauTheme.jade)
            Text(title).font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
        }
        .frame(maxWidth: .infinity, alignment: .leading).padding(16)
        .background(DauTheme.card.opacity(0.72), in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(DauTheme.hairline, lineWidth: 1))
    }
}

struct LearnView: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Your toolkit").font(.system(.title, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
                    NavigationLink {
                        TodayView().toolbar(.hidden, for: .tabBar)
                    } label: {
                        LearnRow(icon: "waveform.path", tint: DauTheme.coral, title: "Tone studio", detail: "See and practise the shape of your tones")
                    }
                    .buttonStyle(.plain)
                    NavigationLink {
                        WordsView().toolbar(.hidden, for: .tabBar)
                    } label: {
                        LearnRow(icon: "character.book.closed.fill", tint: DauTheme.jade, title: "Words", detail: "Explore the six meanings of ma")
                    }
                    .buttonStyle(.plain)
                    Text("Tone results stay separate from conversation practice. A café recording is yours to compare; it is not graded as mastery.")
                        .font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft).padding(.top, 4)
                }.padding(20)
            }.background(DauTheme.ground.ignoresSafeArea()).navigationTitle("Learn").navigationBarTitleDisplayMode(.inline)
        }
    }
}

private struct LearnRow: View {
    let icon: String; let tint: Color; let title: String; let detail: String
    var body: some View {
        HStack(spacing: 15) {
            Image(systemName: icon).font(.system(.title2)).foregroundStyle(tint).frame(width: 48, height: 48).background(tint.opacity(0.12), in: RoundedRectangle(cornerRadius: 15))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
                Text(detail).font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
            }
            Spacer(); Image(systemName: "chevron.right").foregroundStyle(DauTheme.jade)
        }.padding(16).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20)).overlay(RoundedRectangle(cornerRadius: 20).stroke(DauTheme.hairline))
    }
}
