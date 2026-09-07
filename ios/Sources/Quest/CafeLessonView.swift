import DauCore
import SwiftUI

struct CafeLessonView: View {
    let initialStep: CafeLessonStep
    var isReview = false

    @Environment(QuestProgressStore.self) private var quest
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var step: CafeLessonStep
    @State private var audio = QuestAudio()
    @State private var session = CafeQuestSession(availableItems: [.water])
    @State private var feedback: String?
    @State private var showMeaning = false
    @State private var intendedDrink: CafeDrink?
    @State private var listeningCorrect = false
    @State private var transcriptExpanded = false

    init(initialStep: CafeLessonStep, isReview: Bool = false) {
        self.initialStep = initialStep
        self.isReview = isReview
        _step = State(initialValue: initialStep)
    }

    var body: some View {
        NavigationStack {
            ZStack {
                DauTheme.ground.ignoresSafeArea()
                ScrollView {
                    VStack(alignment: .leading, spacing: 22) {
                        progress
                        content
                    }
                    .padding(.horizontal, 22)
                    .padding(.bottom, 30)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { dismiss() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel("Save and close")
                }
                ToolbarItem(placement: .principal) {
                    Text("At the café").font(.system(.subheadline, design: .rounded).weight(.bold))
                }
            }
            .toolbarBackground(DauTheme.ground, for: .navigationBar)
        }
        .tint(DauTheme.jade)
        .onAppear {
            if !isReview { quest.saveStep(step.rawValue) }
            if step == .changedOrder {
                if let saved = quest.snapshot.cafeSession { session = saved }
                else { startChangedScene() }
            }
        }
        .onDisappear { audio.stop() }
        .onChange(of: audio.hasRecording) { wasReady, isReady in
            if !wasReady && isReady { quest.recordSpeakingAttempt() }
        }
    }

    private var progress: some View {
        HStack(spacing: 6) {
            ForEach(CafeLessonStep.allCases) { item in
                Capsule().fill(item.rawValue <= step.rawValue ? DauTheme.coral : DauTheme.jade.opacity(0.16)).frame(height: 6)
            }
        }
        .padding(.top, 8)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Step \(step.rawValue + 1) of \(CafeLessonStep.allCases.count)")
    }

    @ViewBuilder private var content: some View {
        switch step {
        case .welcome: welcome
        case .prepare: prepare
        case .observe: observe
        case .listen: listening
        case .request: requestPractice
        case .repair: repair
        case .changedOrder: changedOrder
        case .finish: finish
        }
    }

    private var heading: some View {
        Text(step.title).font(.system(.largeTitle, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink).fixedSize(horizontal: false, vertical: true)
    }

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Image("cafe-scene").resizable().scaledToFill().frame(height: 220).clipShape(RoundedRectangle(cornerRadius: 26))
            Text("You’ll order a drink, handle a change, and confirm what you’re getting.")
                .font(.system(.body, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
            VStack(spacing: 10) {
                pathButton(.beginner, detail: "Meet the words first · about 12 min")
                pathButton(.heritage, detail: "Try listening first · about 8 min")
            }
            Text("Both paths reach the same café conversation. You can use help whenever you need it.")
                .font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
        }
    }

    private func pathButton(_ path: LearnerPath, detail: String) -> some View {
        Button {
            quest.choosePath(path)
            advance(to: path == .heritage ? .listen : .prepare)
        } label: {
            HStack(spacing: 14) {
                Image(systemName: path == .beginner ? "sparkles" : "ear.fill").font(.system(.title2)).foregroundStyle(path == .beginner ? DauTheme.coral : DauTheme.jade)
                VStack(alignment: .leading, spacing: 3) {
                    Text(path.title).font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
                    Text(detail).font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
                }
                Spacer(); Image(systemName: "arrow.right")
            }.padding(17).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        }.buttonStyle(.plain).accessibilityIdentifier(path == .beginner ? "beginnerPath" : "heritagePath")
    }

    private var prepare: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text("Tap each drink. Listen to the complete request, then say it if you’d like.").questBody()
            drinkCard(.coffee, vietnamese: "cà phê", clip: "C02")
            drinkCard(.water, vietnamese: "nước", clip: "C03")
            languageNote
            primary("Watch a café order") { advance(to: .observe) }
            secondary("Skip preparation") { advance(to: .observe) }
        }
    }

    private func drinkCard(_ drink: CafeDrink, vietnamese: String, clip: String) -> some View {
        Button { audio.playClip(clip) } label: {
            HStack(spacing: 16) {
                Image(systemName: drink == .coffee ? "cup.and.saucer.fill" : "drop.fill")
                    .font(.system(.largeTitle)).foregroundStyle(drink == .coffee ? DauTheme.coral : DauTheme.jade)
                    .frame(width: 58, height: 58).background(DauTheme.ground, in: RoundedRectangle(cornerRadius: 18))
                VStack(alignment: .leading, spacing: 2) {
                    Text(vietnamese).font(.system(.title, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
                    Text(drink == .coffee ? "coffee" : "water").questCaption()
                }
                Spacer(); Image(systemName: "speaker.wave.2.fill").foregroundStyle(DauTheme.jade)
            }.padding(16).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 22))
        }.buttonStyle(.plain).accessibilityIdentifier("listening-\(drink.rawValue)")
    }

    private var languageNote: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("CHO CON…").questSectionTitle()
            Text("Here you’re speaking with an older server. In this example, you call her cô and refer to yourself as con. “Cho con…” is a useful way to ask for something.").questBody()
        }.padding(17).background(DauTheme.jade.opacity(0.10), in: RoundedRectangle(cornerRadius: 20))
    }

    private var observe: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text("Listen to a short water order. Replay each turn as often as you want.").questBody()
            dialogue("Cô · server", "Con muốn nước hay cà phê?", "Would you like water or coffee?", "C01")
            dialogue("You", "Dạ, cho con nước. Cảm ơn cô.", "Water for me, please. Thank you.", "C03")
            dialogue("Cô · server", "Một ly nước, đúng không con?", "One glass of water, right?", "C06")
            dialogue("You", "Dạ, đúng rồi.", "Yes, that’s right.", "C08")
            audioMessage
            primary("Try a listening check") { advance(to: .listen) }
        }
    }

    private func dialogue(_ speaker: String, _ vietnamese: String, _ english: String, _ clip: String) -> some View {
        Button { audio.playClip(clip) } label: {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(speaker.uppercased()).questSectionTitle()
                    Text(vietnamese).font(.system(.title3, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink).multilineTextAlignment(.leading)
                    Text(english).font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft).multilineTextAlignment(.leading)
                }
                Spacer(); Image(systemName: "play.fill").foregroundStyle(DauTheme.jade)
            }.padding(16).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 20))
        }.buttonStyle(.plain)
    }

    private var listening: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text(isReview ? "Which drink did the customer ask for?" : "Listen before revealing the words. Which drink did the customer ask for?").questBody()
            Button { audio.playClip(isReview ? "C03" : "C02") } label: {
                Label("Play the request", systemImage: "speaker.wave.2.fill").questPrimaryButton(fill: DauTheme.jade)
            }
            choice("Coffee", drink: .coffee)
            choice("Water", drink: .water)
            if let feedback { feedbackCard(feedback) }
            DisclosureGroup("Show transcript", isExpanded: $transcriptExpanded) {
                Text(isReview ? "Dạ, cho con nước. Cảm ơn cô." : "Dạ, cho con cà phê. Cảm ơn cô.").font(.system(.body, design: .rounded).weight(.bold)).padding(.top, 10)
            }.tint(DauTheme.jade).foregroundStyle(DauTheme.ink)
                .onChange(of: transcriptExpanded) { _, shown in if shown { session.useAssistance(.transcript) } }
            audioMessage
            if listeningCorrect {
                if isReview { primary("Finish revisit") { quest.completeReview(); dismiss() } }
                else { primary("Learn the request") { advance(to: .request) } }
            }
        }
    }

    private func choice(_ title: String, drink: CafeDrink) -> some View {
        Button {
            intendedDrink = drink
            let target: CafeDrink = isReview ? .water : .coffee
            listeningCorrect = drink == target
            quest.recordListeningChoice(correct: listeningCorrect, assisted: transcriptExpanded || session.pendingAssistance.contains(.transcript) || quest.snapshot.listeningObservations.last?.correct == false, review: isReview)
            feedback = listeningCorrect ? "Yes. The customer asked for \(target == .coffee ? "coffee" : "water")." : "Listen once more. The other drink was requested."
        } label: {
            HStack { Text(title); Spacer(); if intendedDrink == drink { Image(systemName: listeningCorrect ? "checkmark.circle.fill" : "arrow.counterclockwise.circle.fill") } }
                .font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink).padding(18)
                .background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
                .overlay(RoundedRectangle(cornerRadius: 18).stroke(intendedDrink == drink ? DauTheme.jade : DauTheme.hairline, lineWidth: 1.5))
        }.buttonStyle(.plain)
            .accessibilityIdentifier("listening-\(drink.rawValue)")
    }

    private var requestPractice: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text("Ask for coffee. Record yourself, then compare your take with the example.").questBody()
            phraseCard("Dạ, cho con cà phê. Cảm ơn cô.", meaning: "Coffee for me, please. Thank you.", clip: "C02")
            recordingControls(action: .request(.coffee))
            audioMessage
            primary("Continue") { advance(to: .repair) }
        }
    }

    private var repair: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text("You don’t have to guess. Ask the server to repeat the whole turn.").questBody()
            phraseCard("Cô nói lại giùm con.", meaning: "Please say that again for me.", clip: "C05")
            recordingControls(action: .repeatRequest(vietnamese: true))
            audioMessage
            primary("Enter the café") { advance(to: .changedOrder); startChangedScene() }
        }
    }

    private var changedOrder: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            Text(scenePrompt).questBody()
            if let line = currentServerLine { dialogue("Cô · server", showMeaning ? line.vietnamese : "Listen to the server", showMeaning ? line.english : "Use Transcript & meaning if you need it", line.id) }
            HStack {
                Button("Play again") { replayServer() }
                Spacer()
                Button(showMeaning ? "Hide transcript" : "Transcript & meaning") { showMeaning.toggle(); session.useAssistance(.meaning); session.useAssistance(.transcript); quest.saveSession(session) }
            }.font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.jade)
            sceneChoices
            if let feedback { feedbackCard(feedback) }
            audioMessage
            if session.phase == .completed { primary("See what you practised") { advance(to: .finish) } }
        }
    }

    private var scenePrompt: String {
        switch session.phase {
        case .awaitRequest: "Your goal is coffee. Say or think your response, then confirm what you meant."
        case .awaitAlternative: "Coffee is unavailable. What would you like to do?"
        case .awaitConfirmation: "The server read back your order. Confirm it or ask her to repeat."
        case .endedWithoutPurchase: "You ended this exchange without ordering. That is a valid choice; retry the mission to practise the changed order."
        case .completed: "You completed the changed order."
        default: "Start the café exchange."
        }
    }

    private var currentServerLine: CafeLine? {
        guard let id = session.lastServerLineID else { return nil }
        return CafeEpisode.content.lines.first { $0.id == id }
    }

    @ViewBuilder private var sceneChoices: some View {
        switch session.phase {
        case .awaitRequest:
            sceneButton("I mean coffee", action: .request(.coffee))
        case .awaitAlternative:
            sceneButton("Choose water instead", action: .request(.water))
            sceneButton("Ask her to repeat", action: .repeatRequest(vietnamese: false))
            sceneButton("End without ordering", action: .declineWater)
        case .awaitConfirmation:
            sceneButton("Yes, that’s right", action: .confirm)
            sceneButton("Ask her to repeat", action: .repeatRequest(vietnamese: false))
        case .endedWithoutPurchase:
            Button("Retry the changed order") { startChangedScene() }
                .font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.jade)
        default: EmptyView()
        }
    }

    private func sceneButton(_ title: String, action: CafeLearnerAction) -> some View {
        Button {
            let result = session.submit(action)
            quest.saveSession(session)
            feedback = result.feedback
            if let clip = result.lineIDToPlay { audio.playClip(clip) }
        } label: {
            HStack { Text(title); Spacer(); Image(systemName: "arrow.right") }.font(.system(.body, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink).padding(17).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
            .accessibilityIdentifier("scene-\(title.lowercased().replacingOccurrences(of: " ", with: "-"))")
    }

    private var finish: some View {
        VStack(alignment: .leading, spacing: 18) {
            heading
            ZStack {
                Circle().fill(DauTheme.jade.opacity(0.12)).frame(width: 110, height: 110)
                Image(systemName: "cup.and.saucer.fill").font(.system(size: 46)).foregroundStyle(DauTheme.jade)
            }.frame(maxWidth: .infinity).accessibilityHidden(true)
            summaryRow("Practised", "Requesting coffee and water", "text.bubble.fill")
            summaryRow("Handled", "Coffee unavailable, then chose water", "arrow.triangle.branch")
            summaryRow("Listening", listeningSummary, "ear.fill")
            summaryRow("Speaking", "\(quest.snapshot.speakingAttempts) recorded attempt\(quest.snapshot.speakingAttempts == 1 ? "" : "s") to compare · not pronunciation-assessed", "waveform")
            Text("This mission practised one café exchange. It does not assess fluency or readiness for every café conversation.").font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft)
            primary("Finish mission") { quest.completeCafe(); dismiss() }
        }
    }

    private var listeningSummary: String {
        let correct = quest.snapshot.listeningObservations.filter(\.correct)
        let independent = correct.filter { !$0.assisted }.count
        let assisted = correct.filter(\.assisted).count
        if independent > 0 && assisted > 0 { return "\(independent) meaning choice without help · \(assisted) with transcript help" }
        if independent > 0 { return "\(independent) meaning choice\(independent == 1 ? "" : "s") without help" }
        if assisted > 0 { return "\(assisted) meaning choice\(assisted == 1 ? "" : "s") with transcript help" }
        return "No correct meaning choice recorded yet"
    }

    private func phraseCard(_ phrase: String, meaning: String, clip: String) -> some View {
        VStack(alignment: .leading, spacing: 9) {
            Text(phrase).font(.system(.title, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink)
            Text(meaning).questCaption()
            Button { audio.playClip(clip) } label: { Label("Hear the example", systemImage: "speaker.wave.2.fill") }.font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.jade)
        }.padding(18).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 22))
    }

    private func recordingControls(action: CafeLearnerAction) -> some View {
        VStack(spacing: 12) {
            Button {
                Task {
                    let completed = await audio.toggleRecording()
                    feedback = audio.message
                    if completed {
                        var local = CafeQuestSession()
                        feedback = local.submit(action, modality: .spokenRecording).feedback
                    }
                }
            } label: {
                Label(audio.isRecording ? "Stop recording" : "Record my voice", systemImage: audio.isRecording ? "stop.fill" : "mic.fill").questPrimaryButton(fill: audio.isRecording ? DauTheme.coral : DauTheme.jade)
            }
            if audio.hasRecording {
                Button { audio.replayTake() } label: { Label("Replay my take", systemImage: "play.fill") }
                    .font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.jade)
                Text("Your take was recorded. Compare it with the example, then continue when you’re ready.").font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.inkSoft).multilineTextAlignment(.center)
            }
        }
    }

    @ViewBuilder private var audioMessage: some View {
        if let message = ((step == .request || step == .repair) ? feedback : nil) ?? audio.message { Text(message).font(.system(.footnote, design: .rounded)).foregroundStyle(DauTheme.coral).fixedSize(horizontal: false, vertical: true) }
    }

    private func feedbackCard(_ value: String) -> some View {
        Text(value).font(.system(.subheadline, design: .rounded).weight(.semibold)).foregroundStyle(DauTheme.ink).padding(15).frame(maxWidth: .infinity, alignment: .leading).background(DauTheme.jade.opacity(0.10), in: RoundedRectangle(cornerRadius: 16))
    }

    private func summaryRow(_ title: String, _ detail: String, _ icon: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: icon).foregroundStyle(DauTheme.jade).frame(width: 40, height: 40).background(DauTheme.jade.opacity(0.10), in: Circle())
            VStack(alignment: .leading, spacing: 2) { Text(title).font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.ink); Text(detail).questCaption() }
        }.padding(15).background(DauTheme.card, in: RoundedRectangle(cornerRadius: 18))
    }

    private func primary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { HStack { Text(title); Spacer(); Image(systemName: "arrow.right") }.questPrimaryButton() }
            .accessibilityIdentifier("quest-primary-\(step.rawValue)")
    }

    private func secondary(_ title: String, action: @escaping () -> Void) -> some View {
        Button(title, action: action).font(.system(.subheadline, design: .rounded).weight(.bold)).foregroundStyle(DauTheme.jade).frame(maxWidth: .infinity)
    }

    private func advance(to next: CafeLessonStep) {
        audio.stop()
        feedback = nil; intendedDrink = nil; showMeaning = false
        step = next
        quest.saveStep(next.rawValue)
    }

    private func startChangedScene() {
        session = CafeQuestSession(availableItems: [.water])
        let result = session.submit(.start)
        quest.saveSession(session)
        feedback = result.feedback
        if let clip = result.lineIDToPlay { audio.playClip(clip) }
    }

    private func replayServer() {
        guard let id = session.lastServerLineID else { return }
        session.useAssistance(.replayButton)
        quest.saveSession(session)
        audio.playClip(id)
    }
}
