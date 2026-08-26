import Foundation

/// Every user-facing word about a verdict. Lives in DauCore so the honesty constraints are
/// unit-testable without launching a simulator — nothing in the app layer may compose these
/// strings itself.
///
/// Tone of voice, from the design: meaning first, then acoustics, then exactly one physical
/// fix. Never scold, never fake certainty, never say "score".
public enum VerdictCopy {
    /// What a word means, supplied by the content layer so copy can say "ghost" not "ngang".
    public struct Word: Equatable, Sendable {
        public let surface: String
        public let meaning: String
        public init(surface: String, meaning: String) {
            self.surface = surface
            self.meaning = meaning
        }
    }

    /// The banner above the headline.
    public static func eyebrow(for verdict: ToneVerdict) -> String {
        switch verdict.outcome {
        case .matched: "Verified · dấu \(verdict.target.label)"
        case .missedNaming, .missedShape: "Not it yet"
        case .inconclusive: "Didn't catch that"
        }
    }

    /// The big line. `produced` names the word the learner actually said, when one is known.
    public static func headline(
        for verdict: ToneVerdict,
        target: Word,
        produced: Word?
    ) -> String {
        switch verdict.outcome {
        case .matched:
            return "That's \(target.surface) — \(target.meaning)"
        case .missedNaming:
            // The brand moment. Only reachable when the produced family resolves to exactly
            // one tone for this accent, so the claim is as solid as the verdict itself.
            if let produced {
                return "You said \(produced.surface) — \(produced.meaning)"
            }
            return physicalHeadline(for: verdict)
        case .missedShape:
            return physicalHeadline(for: verdict)
        case .inconclusive(let reason):
            switch reason {
            case .weakSignal: return "That one came through too faint"
            case .contradictoryEvidence: return "That one didn't read clearly"
            case .unclearShape: return "No clear shape in that take"
            }
        }
    }

    /// The supporting sentence: what happened, in terms of the shape.
    public static func detail(for verdict: ToneVerdict, target: Word) -> String {
        switch verdict.outcome {
        case .matched:
            return "\(matchedShapeSentence(for: verdict.target)) Exactly the word you meant."
        case .missedNaming, .missedShape:
            return physicalCue(for: verdict.target)
        case .inconclusive(let reason):
            switch reason {
            case .weakSignal:
                return "Get a little closer to the mic and give \(target.surface) another go."
            case .contradictoryEvidence:
                // Honest abstention, said plainly. This is the state competitors paper over.
                return "The pitch and the shape disagreed, so we'd rather not guess. Try once more."
            case .unclearShape:
                return "A longer, steadier syllable reads better. Try \(target.surface) again."
            }
        }
    }

    /// When the produced shape doesn't name a word, describe it and offer the pair it could
    /// have been — never picking one.
    public static func ambiguityNote(for verdict: ToneVerdict, candidates: [Word]) -> String? {
        guard case .missedShape(let family) = verdict.outcome, candidates.count > 1 else {
            return nil
        }
        let names = candidates.map(\.surface).joined(separator: " or ")
        return "That came out \(family.shapeDescription) — the \(names) shape, "
            + "not the \(verdict.target.hint) \(verdict.target.label) needs."
    }

    /// The one physical correction. Kept to a single instruction on purpose.
    public static func physicalCue(for tone: ToneMark) -> String {
        switch tone {
        case .ngang: "Hold it steady — one flat note, no drift up or down."
        case .sac: "Start mid, then lift through the vowel — like asking \"yeah?\""
        case .huyen: "Start mid and let it sink, breathy and relaxed to the bottom."
        case .hoi: "Dip down, then come back up — like a doubtful \"hmm?\""
        case .nga: "Break it in the middle — a catch in the throat, then push up."
        case .nang: "Short and low. Drop straight down and stop."
        }
    }

    private static func physicalHeadline(for verdict: ToneVerdict) -> String {
        switch verdict.target {
        case .ngang: "It drifted off the level"
        case .sac: "The rise didn't land"
        case .huyen: "The fall didn't land"
        case .hoi: "The dip didn't come back"
        case .nga: "The break didn't come through"
        case .nang: "It didn't drop and stop"
        }
    }

    private static func matchedShapeSentence(for tone: ToneMark) -> String {
        switch tone {
        case .ngang: "Held level."
        case .sac: "Clean rise."
        case .huyen: "Clean fall."
        case .hoi: "Dipped and recovered."
        case .nga: "The break came through."
        case .nang: "Short and low."
        }
    }

    /// The provenance line under the verdict. Two things it must always convey: grading is
    /// local, and no per-tone confidence is being claimed.
    public static func provenance(for verdict: ToneVerdict) -> String {
        switch verdict.outcome {
        case .matched:
            return "\(verdict.target.label) detected · graded on this iPhone"
        case .missedNaming, .missedShape:
            return "\(verdict.target.label) not detected · graded on this iPhone"
        case .inconclusive:
            return "no verdict · graded on this iPhone"
        }
    }

    /// How the shape-match number is labelled. A single place, so the word "score" cannot
    /// leak into the product by accident.
    public static func shapeMatchLabel(_ match: ShapeMatch) -> String {
        "\(match.percent)% shape match"
    }
}
