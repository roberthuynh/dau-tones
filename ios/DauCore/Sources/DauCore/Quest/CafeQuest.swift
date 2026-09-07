import Foundation

public enum CafeDrink: String, Codable, Sendable, CaseIterable {
    case coffee
    case water
}

public enum CafeSpeaker: String, Codable, Sendable {
    case server
    case learnerModel
}

public struct CafeLine: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let speaker: CafeSpeaker
    public let vietnamese: String
    public let english: String
    public let audioKey: String?

    public init(id: String, speaker: CafeSpeaker, vietnamese: String, english: String, audioKey: String?) {
        self.id = id
        self.speaker = speaker
        self.vietnamese = vietnamese
        self.english = english
        self.audioKey = audioKey
    }
}

public enum CafeActivityKind: String, Codable, Sendable {
    case preparation
    case listening
    case supportedExchange
    case changedExchange
    case review
}

public struct CafeActivity: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let kind: CafeActivityKind
    public let title: String
    public let lineIDs: [String]
    public let optional: Bool

    public init(id: String, kind: CafeActivityKind, title: String, lineIDs: [String], optional: Bool = false) {
        self.id = id
        self.kind = kind
        self.title = title
        self.lineIDs = lineIDs
        self.optional = optional
    }
}

public struct CafeEpisode: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let revision: Int
    public let title: String
    public let canDo: String
    public let lines: [CafeLine]
    public let activities: [CafeActivity]

    public static let content = CafeEpisode(
        id: "cafe-01",
        revision: 1,
        title: "At the café",
        canDo: "Request a drink, understand when coffee is unavailable, choose water, and confirm the order.",
        lines: [
            .init(id: "C01", speaker: .server, vietnamese: "Con muốn nước hay cà phê?", english: "Would you like water or coffee?", audioKey: "C01"),
            .init(id: "C02", speaker: .learnerModel, vietnamese: "Dạ, cho con cà phê. Cảm ơn cô.", english: "Coffee for me, please. Thank you.", audioKey: "C02"),
            .init(id: "C03", speaker: .learnerModel, vietnamese: "Dạ, cho con nước. Cảm ơn cô.", english: "Water for me, please. Thank you.", audioKey: "C03"),
            .init(id: "C04", speaker: .server, vietnamese: "Cà phê hết rồi con. Con uống nước được không?", english: "We're out of coffee. Would water be okay?", audioKey: "C04"),
            .init(id: "C05", speaker: .learnerModel, vietnamese: "Cô nói lại giùm con.", english: "Please say that again for me.", audioKey: "C05"),
            .init(id: "C06", speaker: .server, vietnamese: "Một ly nước, đúng không con?", english: "One glass of water, right?", audioKey: "C06"),
            .init(id: "C07", speaker: .server, vietnamese: "Một ly cà phê, đúng không con?", english: "One cup of coffee, right?", audioKey: "C07"),
            .init(id: "C08", speaker: .learnerModel, vietnamese: "Dạ, đúng rồi.", english: "Yes, that's right.", audioKey: "C08"),
        ],
        activities: [
            .init(id: "cafe-01-preparation", kind: .preparation, title: "Coffee, water, and Cho con…", lineIDs: ["C02", "C03"], optional: true),
            .init(id: "cafe-01-listen", kind: .listening, title: "Hear which drink was requested", lineIDs: ["C02", "C03"]),
            .init(id: "cafe-01-supported", kind: .supportedExchange, title: "Order coffee or water", lineIDs: ["C01", "C02", "C03", "C06", "C07", "C08"]),
            .init(id: "cafe-01-changed", kind: .changedExchange, title: "Coffee is unavailable", lineIDs: ["C01", "C02", "C04", "C05", "C03", "C06", "C08"]),
            .init(id: "cafe-01-review", kind: .review, title: "Try the useful difficulty again", lineIDs: ["C04", "C05", "C06", "C08"]),
        ]
    )
}

public enum CafeScenePhase: String, Codable, Sendable {
    case greet
    case awaitRequest
    case awaitAlternative
    case awaitConfirmation
    case completed
    case endedWithoutPurchase
}

public enum CafeLearnerAction: Codable, Equatable, Sendable {
    case start
    case request(CafeDrink)
    case acceptOfferedWater
    case repeatRequest(vietnamese: Bool)
    case confirm
    case declineWater
    case unclear
}

public enum CafeResponseModality: String, Codable, Sendable {
    case meaningChoice
    case typed
    case spokenRecording
}

public enum CafeAssistance: String, Codable, Sendable, CaseIterable {
    case phraseHint
    case transcript
    case meaning
    case answerReveal
    case replayButton
    case intendedMeaningConfirmation
}

public enum CafeEvidenceLevel: String, Codable, Sendable {
    case independent
    case assisted
    case rehearsal
    case unassessed
}

public struct CafeAttempt: Codable, Equatable, Sendable, Identifiable {
    public let id: Int
    public let phase: CafeScenePhase
    public let action: CafeLearnerAction
    public let modality: CafeResponseModality
    public let assistance: Set<CafeAssistance>
    public let accepted: Bool?
    public let evidence: CafeEvidenceLevel

    public init(id: Int, phase: CafeScenePhase, action: CafeLearnerAction, modality: CafeResponseModality, assistance: Set<CafeAssistance>, accepted: Bool?, evidence: CafeEvidenceLevel) {
        self.id = id
        self.phase = phase
        self.action = action
        self.modality = modality
        self.assistance = assistance
        self.accepted = accepted
        self.evidence = evidence
    }
}

public struct CafeTurnResult: Codable, Equatable, Sendable {
    public let accepted: Bool?
    public let lineIDToPlay: String?
    public let feedback: String
    public let phase: CafeScenePhase
}

public enum CafeQuestSessionError: Error, Equatable, Sendable {
    case waterMustBeAvailable
    case incompatibleEpisode(expectedID: String, expectedRevision: Int, actualID: String, actualRevision: Int)
    case invalidPersistedState
}

public struct CafeQuestSession: Codable, Equatable, Sendable {
    public let episodeID: String
    public let episodeRevision: Int
    public private(set) var phase: CafeScenePhase
    public private(set) var availableItems: Set<CafeDrink>
    public private(set) var requestedItem: CafeDrink?
    public private(set) var confirmedItem: CafeDrink?
    public let quantity: Int
    public private(set) var lastServerLineID: String?
    public private(set) var attempts: [CafeAttempt]
    public private(set) var pendingAssistance: Set<CafeAssistance>
    public private(set) var alternativeCoffeeRetries: Int

    public init(availableItems: Set<CafeDrink> = Set(CafeDrink.allCases)) {
        precondition(availableItems.contains(.water), "The café episode requires water because its changed-order branch offers water.")
        episodeID = CafeEpisode.content.id
        episodeRevision = CafeEpisode.content.revision
        phase = .greet
        self.availableItems = availableItems
        requestedItem = nil
        confirmedItem = nil
        quantity = 1
        lastServerLineID = nil
        attempts = []
        pendingAssistance = []
        alternativeCoffeeRetries = 0
    }

    public init(validatedAvailableItems: Set<CafeDrink>) throws {
        guard validatedAvailableItems.contains(.water) else { throw CafeQuestSessionError.waterMustBeAvailable }
        self.init(availableItems: validatedAvailableItems)
    }

    public static func restore(from data: Data, using decoder: JSONDecoder = JSONDecoder()) throws -> CafeQuestSession {
        let session = try decoder.decode(CafeQuestSession.self, from: data)
        guard session.episodeID == CafeEpisode.content.id, session.episodeRevision == CafeEpisode.content.revision else {
            throw CafeQuestSessionError.incompatibleEpisode(
                expectedID: CafeEpisode.content.id,
                expectedRevision: CafeEpisode.content.revision,
                actualID: session.episodeID,
                actualRevision: session.episodeRevision
            )
        }
        guard session.availableItems.contains(.water), session.quantity == 1, session.hasConsistentState else {
            throw CafeQuestSessionError.invalidPersistedState
        }
        return session
    }

    public mutating func useAssistance(_ assistance: CafeAssistance) {
        pendingAssistance.insert(assistance)
    }

    @discardableResult
    public mutating func revealAnswer() -> CafeTurnResult {
        pendingAssistance.insert(.answerReveal)
        return CafeTurnResult(accepted: nil, lineIDToPlay: modelLineForCurrentPhase, feedback: "This is a model answer. Try it when you're ready.", phase: phase)
    }

    @discardableResult
    public mutating func submit(_ action: CafeLearnerAction, modality: CafeResponseModality = .meaningChoice) -> CafeTurnResult {
        let originalPhase = phase
        var assistance = pendingAssistance
        if case .repeatRequest(vietnamese: false) = action {
            assistance.insert(.replayButton)
        }
        pendingAssistance = []
        if phase == .completed || phase == .endedWithoutPurchase {
            let result = CafeTurnResult(accepted: false, lineIDToPlay: nil, feedback: "This exchange has ended. Start another practice to respond again.", phase: phase)
            attempts.append(.init(id: attempts.count + 1, phase: originalPhase, action: action, modality: modality, assistance: assistance, accepted: false, evidence: assistance.isEmpty ? .independent : .assisted))
            return result
        }
        if modality == .spokenRecording && !assistance.contains(.intendedMeaningConfirmation) {
            let result = CafeTurnResult(accepted: nil, lineIDToPlay: nil, feedback: "Your response was recorded. Compare it with the example or confirm what you meant.", phase: phase)
            attempts.append(.init(id: attempts.count + 1, phase: originalPhase, action: action, modality: modality, assistance: assistance, accepted: nil, evidence: .unassessed))
            return result
        }
        let result = transition(action)
        let evidence: CafeEvidenceLevel
        if assistance.contains(.answerReveal) {
            evidence = .rehearsal
        } else if assistance.isEmpty {
            evidence = .independent
        } else {
            evidence = .assisted
        }
        attempts.append(.init(id: attempts.count + 1, phase: originalPhase, action: action, modality: modality, assistance: assistance, accepted: result.accepted, evidence: evidence))
        return result
    }

    private var modelLineForCurrentPhase: String? {
        switch phase {
        case .awaitRequest: return "C02"
        case .awaitAlternative: return "C03"
        case .awaitConfirmation: return "C08"
        default: return nil
        }
    }

    private var hasConsistentState: Bool {
        switch phase {
        case .greet:
            return requestedItem == nil && confirmedItem == nil && lastServerLineID == nil
        case .awaitRequest:
            return requestedItem == nil && confirmedItem == nil && lastServerLineID == "C01"
        case .awaitAlternative:
            return requestedItem == .coffee && confirmedItem == nil && lastServerLineID == "C04"
        case .awaitConfirmation:
            return requestedItem != nil && confirmedItem == nil && (lastServerLineID == "C06" || lastServerLineID == "C07")
        case .completed:
            return requestedItem != nil && confirmedItem == requestedItem
        case .endedWithoutPurchase:
            return confirmedItem == nil
        }
    }

    private mutating func transition(_ action: CafeLearnerAction) -> CafeTurnResult {
        if case let .repeatRequest(vietnamese) = action, let lastServerLineID {
            return .init(accepted: true, lineIDToPlay: lastServerLineID, feedback: vietnamese ? "You asked the server to repeat." : "Listen again, then respond.", phase: phase)
        }

        switch (phase, action) {
        case (.greet, .start):
            phase = .awaitRequest
            lastServerLineID = "C01"
            return .init(accepted: true, lineIDToPlay: "C01", feedback: "Choose coffee or water.", phase: phase)

        case (.awaitRequest, .request(let drink)) where availableItems.contains(drink):
            requestedItem = drink
            phase = .awaitConfirmation
            lastServerLineID = drink == .water ? "C06" : "C07"
            return .init(accepted: true, lineIDToPlay: lastServerLineID, feedback: "The server reads back your order.", phase: phase)

        case (.awaitRequest, .request(.coffee)):
            requestedItem = .coffee
            phase = .awaitAlternative
            lastServerLineID = "C04"
            return .init(accepted: true, lineIDToPlay: "C04", feedback: "Coffee is unavailable. The server offers water.", phase: phase)

        case (.awaitAlternative, .request(.water)), (.awaitAlternative, .acceptOfferedWater):
            requestedItem = .water
            phase = .awaitConfirmation
            lastServerLineID = "C06"
            return .init(accepted: true, lineIDToPlay: "C06", feedback: "You changed the order to water.", phase: phase)

        case (.awaitAlternative, .request(.coffee)):
            alternativeCoffeeRetries += 1
            lastServerLineID = "C04"
            let feedback = alternativeCoffeeRetries == 1 ? "Coffee is still unavailable. Try choosing water." : "Choose water from the menu, or end the order."
            return .init(accepted: false, lineIDToPlay: "C04", feedback: feedback, phase: phase)

        case (.awaitAlternative, .declineWater):
            phase = .endedWithoutPurchase
            return .init(accepted: true, lineIDToPlay: nil, feedback: "You ended the exchange without buying a drink.", phase: phase)

        case (.awaitConfirmation, .confirm):
            confirmedItem = requestedItem
            phase = .completed
            return .init(accepted: true, lineIDToPlay: nil, feedback: "Order confirmed.", phase: phase)

        case (_, .unclear):
            return .init(accepted: nil, lineIDToPlay: nil, feedback: "That response wasn't assessed. Retry, compare a recording, type, or choose the intended meaning.", phase: phase)

        default:
            return .init(accepted: false, lineIDToPlay: nil, feedback: "That response doesn't complete this turn. Try again.", phase: phase)
        }
    }
}
