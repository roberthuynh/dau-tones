import Foundation

/// Whether the signal supported a judgement at all.
public enum SignalQuality: Equatable, Sendable {
    case usable
    /// Too short, too quiet, or too unvoiced to read.
    case weak
}

/// The result of judging one take against the tone it was aiming at.
public struct ToneVerdict: Equatable, Sendable {
    public enum Outcome: Equatable, Sendable {
        /// The target tone's acceptance rule passed and the shape agrees.
        case matched
        /// The rule failed, and what was produced names exactly one other tone — the "you
        /// said ghost" moment. Only ever populated where the family resolves uniquely for
        /// this accent.
        case missedNaming(ToneMark)
        /// The rule failed and a real shape was read, but it does not resolve to a single
        /// tone (falling is huyền or nặng; Southern dipping is hỏi or ngã, genuinely merged).
        /// Speak about the shape, show both candidates, name neither.
        case missedShape(ToneFamily)
        /// No verdict. Ask for another take rather than guessing.
        case inconclusive(Reason)

        public enum Reason: String, Equatable, Sendable {
            /// Not enough voiced signal.
            case weakSignal
            /// The acceptance rule passed but the shape read contradicts the target, so
            /// neither answer is trustworthy. Most often Southern hỏi/ngã, whose acceptance
            /// rule is loose by inheritance.
            case contradictoryEvidence
            /// Signal was readable but matched no recognizable shape.
            case unclearShape
        }
    }

    public let outcome: Outcome
    public let target: ToneMark
    public let accent: Accent
    /// Reason codes from the acceptance rules; empty when the target's rule passed.
    public let failures: [ToneRuleFailure]
    /// Nil whenever the signal did not support a number, or no reference was available.
    public let shapeMatch: ShapeMatch?
    public let reading: ToneShapeReading?

    public var isMatch: Bool {
        if case .matched = outcome { return true }
        return false
    }

    /// True when the app should ask for another take instead of reporting anything.
    public var isInconclusive: Bool {
        if case .inconclusive = outcome { return true }
        return false
    }
}
