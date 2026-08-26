import DauCore
import SwiftUI

/// The pitch lane: the glowing target, and your line drawn over it.
///
/// Ported from nghe's `ToneCurveView` with one addition that matters — `fixedBounds`.
/// The percentile-adaptive axis is right for a finished verdict, but wrong live: a moving
/// axis makes the target line shift under a learner who is actively trying to track it. While
/// recording, the axis is pinned to the target's span.
struct ToneCurveView: View {
    /// 64-point target contour, or nil when this word has no reference for the accent.
    var target: [Double]?
    /// The learner's line so far, in semitones.
    var learner: [Double]
    /// Pin the axis instead of letting it adapt. Always set during a live take.
    var fixedBounds: ClosedRange<Double>?
    var isLive: Bool = false
    var learnerColor: Color = DauTheme.cream
    var targetColor: Color = DauTheme.coral

    private var bounds: ClosedRange<Double> {
        if let fixedBounds { return fixedBounds }
        let values = (target ?? []) + learner
        guard !values.isEmpty else { return -6...6 }
        // Percentiles, not min/max — one bad frame must not decide the axis, the same rule
        // the judge uses when it measures pitchRange.
        let low = ToneNumerics.percentile(values, 5)
        let high = ToneNumerics.percentile(values, 95)
        let padding = max(1.5, (high - low) * 0.25)
        return (low - padding)...(high + padding)
    }

    static func bounds(forTarget target: [Double]?) -> ClosedRange<Double> {
        guard let target, !target.isEmpty else { return -6...6 }
        let low = target.min() ?? -6
        let high = target.max() ?? 6
        let padding = max(2.0, (high - low) * 0.3)
        return (low - padding)...(high + padding)
    }

    var body: some View {
        GeometryReader { geometry in
            let rect = CGRect(origin: .zero, size: geometry.size)
            ZStack {
                staffLines(in: rect)
                if let target, target.count > 1 {
                    // The glow, then the dashed target on top of it.
                    path(for: target, in: rect)
                        .stroke(targetColor.opacity(0.22), style: .init(lineWidth: 12, lineCap: .round))
                    path(for: target, in: rect)
                        .stroke(
                            targetColor,
                            style: .init(lineWidth: 3.5, lineCap: .round, dash: [7, 8])
                        )
                }
                if learner.count > 1 {
                    path(for: learner, in: rect)
                        .stroke(learnerColor, style: .init(lineWidth: 4, lineCap: .round, lineJoin: .round))
                    head(in: rect)
                }
            }
        }
        .accessibilityElement()
        .accessibilityLabel(accessibilitySummary)
    }

    private func staffLines(in rect: CGRect) -> some View {
        ForEach([0.25, 0.5, 0.75], id: \.self) { fraction in
            Path { path in
                let y = rect.height * fraction
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: rect.width, y: y))
            }
            .stroke(DauTheme.cream.opacity(0.06), lineWidth: 1)
        }
    }

    private func point(_ value: Double, at index: Int, count: Int, in rect: CGRect) -> CGPoint {
        let span = bounds.upperBound - bounds.lowerBound
        let x = count > 1 ? rect.width * CGFloat(index) / CGFloat(count - 1) : rect.midX
        let normalized = span > 0 ? (value - bounds.lowerBound) / span : 0.5
        // Higher pitch draws higher on screen.
        let y = rect.height * (1 - CGFloat(normalized))
        return CGPoint(x: x, y: min(max(y, 2), rect.height - 2))
    }

    private func path(for values: [Double], in rect: CGRect) -> Path {
        var path = Path()
        for (index, value) in values.enumerated() {
            let position = point(value, at: index, count: values.count, in: rect)
            if index == 0 { path.move(to: position) } else { path.addLine(to: position) }
        }
        return path
    }

    private func head(in rect: CGRect) -> some View {
        let position = point(learner[learner.count - 1], at: learner.count - 1, count: learner.count, in: rect)
        return ZStack {
            Circle().fill(learnerColor).frame(width: 14, height: 14)
            if isLive {
                Circle().stroke(learnerColor.opacity(0.35), lineWidth: 2).frame(width: 26, height: 26)
            }
        }
        .position(position)
    }

    private var accessibilitySummary: String {
        guard learner.count > 1, let first = learner.first, let last = learner.last else {
            return "Pitch trace, nothing recorded yet."
        }
        let drift = last - first
        let direction = abs(drift) < 0.75 ? "stayed level" :
            (drift > 0 ? "rose \(abs(drift).rounded(toPlaces: 1)) semitones"
                       : "fell \(abs(drift).rounded(toPlaces: 1)) semitones")
        return "Your pitch \(direction)."
    }
}

private extension Double {
    func rounded(toPlaces places: Int) -> Double {
        let factor = pow(10.0, Double(places))
        return (self * factor).rounded() / factor
    }
}
