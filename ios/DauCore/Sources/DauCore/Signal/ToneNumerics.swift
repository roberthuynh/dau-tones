import Foundation

/// Shared numerics for contour work, ported from nghe's `ToneShape.swift`.
///
/// These match numpy's defaults deliberately — the thresholds in `ToneRuleTable` and
/// `ToneShapeJudge` were calibrated against `dấu`'s Python, and a different percentile
/// convention or slope fit would silently move every one of them.
public enum ToneNumerics {
    /// Contour length the thresholds were calibrated against.
    public static let analysisPoints = 64

    /// Least-squares slope. The x values are the caller's, not renormalized per slice: the
    /// half-slopes are fit against their own portion of the 0...1 axis, and renormalizing
    /// them would scale curvature by two.
    public static func slope(x: [Double], y: [Double]) -> Double {
        guard x.count == y.count, x.count > 1 else { return 0 }
        let meanX = x.reduce(0, +) / Double(x.count)
        let meanY = y.reduce(0, +) / Double(y.count)
        var covariance = 0.0
        var variance = 0.0
        for (xValue, yValue) in zip(x, y) {
            let deltaX = xValue - meanX
            covariance += deltaX * (yValue - meanY)
            variance += deltaX * deltaX
        }
        guard variance > 1e-12 else { return 0 }
        return covariance / variance
    }

    public static func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        let middle = sorted.count / 2
        if sorted.count.isMultiple(of: 2) {
            return (sorted[middle - 1] + sorted[middle]) / 2
        }
        return sorted[middle]
    }

    /// Linear-interpolation percentile, matching numpy's default so the ported thresholds
    /// keep their meaning. Public because the drawing layer sizes its axis the same way the
    /// judge sizes `pitchRange` — one outlier frame must not decide either.
    public static func percentile(_ values: [Double], _ percent: Double) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        guard sorted.count > 1 else { return sorted[0] }
        let position = (percent / 100) * Double(sorted.count - 1)
        let lower = Int(position.rounded(.down))
        let upper = min(lower + 1, sorted.count - 1)
        let fraction = position - Double(lower)
        return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction
    }

    /// Fill unvoiced frames by interpolating between their voiced neighbours, holding the
    /// first and last voiced values at the edges. Dropping them instead would compress the
    /// time axis and move every position feature.
    public static func interpolatingGaps(in contour: [Double?]) -> [Double] {
        let indices = contour.indices.filter { contour[$0] != nil }
        guard let first = indices.first, let last = indices.last else { return [] }
        var filled: [Double] = []
        filled.reserveCapacity(contour.count)
        var previous = first
        for index in contour.indices {
            if index <= first { filled.append(contour[first]!); continue }
            if index >= last { filled.append(contour[last]!); continue }
            if let value = contour[index] {
                filled.append(value)
                previous = index
                continue
            }
            let next = indices.first { $0 > index } ?? last
            let span = Double(next - previous)
            let progress = span > 0 ? Double(index - previous) / span : 0
            let low = contour[previous]!
            let high = contour[next]!
            filled.append(low + (high - low) * progress)
        }
        return filled
    }

    /// Linear resampling onto a normalized axis.
    public static func resampled(_ values: [Double], to count: Int) -> [Double] {
        guard count > 0 else { return [] }
        guard values.count > 1 else {
            return Array(repeating: values.first ?? 0, count: count)
        }
        return (0..<count).map { destination in
            let position = Double(destination) * Double(values.count - 1) / Double(count - 1)
            let lower = Int(position.rounded(.down))
            let upper = min(lower + 1, values.count - 1)
            let fraction = position - Double(lower)
            return values[lower] + (values[upper] - values[lower]) * fraction
        }
    }
}

extension Double {
    func rounded(toPlaces places: Int) -> Double {
        let factor = pow(10.0, Double(places))
        return (self * factor).rounded() / factor
    }
}
