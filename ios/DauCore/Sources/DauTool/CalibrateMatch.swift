import DauCore
import Foundation

/// Recomputes the scale constant behind `ShapeMatch`.
///
/// The number Dấu shows has to come from measured variation, not a guess. This reports how
/// far apart two takes of the *same* tone sit versus two takes of *different* tones, and what
/// a candidate scale turns those into, so the constant in `ShapeMatch.scaleSemitones` can be
/// defended rather than asserted.
enum CalibrateMatch {
    struct Fixtures: Decodable {
        struct Take: Decodable {
            let wordID: String
            let tone: String
            let accent: String
            let contour: [Double]
        }
        let takes: [Take]
    }

    static func run(fixtures path: String) throws {
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let takes = try JSONDecoder().decode(Fixtures.self, from: data).takes

        var sameTone: [Double] = []
        var differentTone: [Double] = []
        for (indexA, a) in takes.enumerated() {
            for b in takes[(indexA + 1)...] where a.accent == b.accent {
                let deviation = rms(a.contour, b.contour)
                if a.tone == b.tone { sameTone.append(deviation) } else { differentTone.append(deviation) }
            }
        }

        print("within-accent pairs: \(sameTone.count) same-tone, \(differentTone.count) different-tone")
        report("same tone", sameTone)
        report("different tone", differentTone)
        print("\ncurrent scale: \(ShapeMatch.scaleSemitones) semitones")
        for scale in [6.0, 8.0, 10.0, 12.0] {
            let same = percent(median(sameTone), scale: scale)
            let different = percent(median(differentTone), scale: scale)
            let marker = scale == ShapeMatch.scaleSemitones ? "  <- current" : ""
            print(String(
                format: "  scale %.0f -> same-tone median %d%%, different-tone median %d%%%@",
                scale, same, different, marker
            ))
        }
        print("""

        Pick a scale where a same-tone take reads as a good match and a different tone reads
        clearly worse. Note these pairs are different *words* sharing a tone, which varies more
        than one learner repeating one word against its own reference — real drilling should sit
        above these numbers.
        """)
    }

    private static func report(_ label: String, _ values: [Double]) {
        guard !values.isEmpty else { return }
        let sorted = values.sorted()
        print(String(
            format: "  %-15s n=%4d median=%5.2f p10=%5.2f p90=%5.2f max=%5.2f",
            (label as NSString).utf8String!, sorted.count, median(sorted),
            sorted[sorted.count / 10], sorted[9 * sorted.count / 10], sorted.last!
        ))
    }

    private static func percent(_ deviation: Double, scale: Double) -> Int {
        Int((max(0, min(1, 1 - deviation / scale)) * 100).rounded())
    }

    private static func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        return sorted[sorted.count / 2]
    }

    private static func rms(_ a: [Double], _ b: [Double]) -> Double {
        guard a.count == b.count, !a.isEmpty else { return .infinity }
        return (zip(a, b).map { ($0 - $1) * ($0 - $1) }.reduce(0, +) / Double(a.count)).squareRoot()
    }
}
