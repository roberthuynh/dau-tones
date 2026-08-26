import DauCore
import SwiftUI

/// Pitch-contour glyph for a Vietnamese tone — the eye's anchor for what the ear heard.
/// Drawn in a 36×20 design space. Decorative; the tone label always carries the meaning.
///
/// Ported from nghe's `ToneContourGlyph`, retinted for the dark ground.
struct ToneContourGlyph: View {
    let tone: ToneMark
    var width: CGFloat = 44
    var color: Color?

    var body: some View {
        let ink = color ?? DauTheme.toneColor(tone)
        ZStack {
            ToneContourShape(tone: tone)
                .stroke(ink, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            if tone == .nang {
                // The glottal stop: a heavy dot after the drop.
                Circle().fill(ink)
                    .frame(width: width * 0.11, height: width * 0.11)
                    .position(x: width * (27.0 / 36.0), y: width * (20.0 / 36.0) * (16.0 / 20.0))
            }
        }
        .frame(width: width, height: width * 20 / 36)
        .accessibilityHidden(true)
    }
}

/// The six contours, unit-scaled from the design's 36×20 paths.
struct ToneContourShape: Shape {
    let tone: ToneMark

    func path(in rect: CGRect) -> Path {
        func pt(_ x: CGFloat, _ y: CGFloat) -> CGPoint {
            CGPoint(x: rect.minX + rect.width * x / 36, y: rect.minY + rect.height * y / 20)
        }
        var path = Path()
        switch tone {
        case .ngang:
            path.move(to: pt(3, 8)); path.addLine(to: pt(33, 8))
        case .sac:
            path.move(to: pt(3, 15)); path.addLine(to: pt(33, 4))
        case .huyen:
            path.move(to: pt(3, 6)); path.addLine(to: pt(33, 15))
        case .hoi:
            path.move(to: pt(3, 5))
            path.addCurve(to: pt(33, 8), control1: pt(12, 19), control2: pt(24, 19))
        case .nga:
            path.move(to: pt(3, 14)); path.addLine(to: pt(14, 8))
            path.move(to: pt(20, 11)); path.addLine(to: pt(33, 3))
        case .nang:
            path.move(to: pt(3, 6)); path.addLine(to: pt(20, 14))
        }
        return path
    }
}

extension ToneMark {
    /// One-word English contour descriptor.
    var contourDescriptor: String {
        switch self {
        case .ngang: "FLAT"
        case .sac: "RISE"
        case .huyen: "FALL"
        case .hoi: "DIP"
        case .nga: "BREAK"
        case .nang: "DROP"
        }
    }

    /// The mark whose glyph stands in for this tone in a Southern context — ngã borrows
    /// hỏi's dip, because in the South they are one spoken tone and must never look like
    /// two different answers.
    func glyphMark(for accent: Accent) -> ToneMark {
        accent == .south && self == .nga ? .hoi : self
    }
}
