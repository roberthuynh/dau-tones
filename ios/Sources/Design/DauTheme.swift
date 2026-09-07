import DauCore
import SwiftUI

/// Warm paper, jade, and coral tokens for the illustrated Vietnam mission experience.
public enum DauTheme {
    public static let ground = Color(hex: 0xF8F1E3)
    public static let groundDeep = Color(hex: 0xEDE1CB)
    public static let card = Color(hex: 0xFFFDF8)
    public static let well = Color(hex: 0xEFE5D4)
    /// Primary action + brand.
    public static let coral = Color(hex: 0xB9473F)
    /// Text on a coral fill.
    public static let onCoral = Color.white
    public static let cream = Color(hex: 0x2A302A)
    public static let ink = Color(hex: 0x2A302A)
    public static let inkSoft = Color(hex: 0x48534A)
    public static let muted = inkSoft
    public static let faint = Color(hex: 0x666A61)
    public static let jade = Color(hex: 0x397D6B)
    public static let jadeDark = Color(hex: 0x245849)
    /// Verified / matched.
    public static let verified = Color(hex: 0x287363)
    /// Didn't match.
    public static let missed = Color(hex: 0xB33A31)

    public static let hairline = Color(hex: 0x2A302A).opacity(0.10)
}

public extension DauTheme {
    /// Tone accents tuned for readable contrast on the warm paper background.
    static func toneColor(_ tone: ToneMark) -> Color {
        switch tone {
        case .ngang: Color(hex: 0x806636)
        case .huyen: Color(hex: 0x375FAB)
        case .sac: Color(hex: 0xB9473F)
        case .hoi: Color(hex: 0x77509B)
        case .nga: Color(hex: 0x287363)
        case .nang: Color(hex: 0x966015)
        }
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}

extension View {
    func questEyebrow(color: Color = DauTheme.jade) -> some View {
        self.font(.system(.caption, design: .rounded).weight(.heavy))
            .tracking(1.4)
            .foregroundStyle(color)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(DauTheme.card.opacity(0.94), in: Capsule())
    }

    func questSectionTitle() -> some View {
        self.font(.system(.caption, design: .rounded).weight(.heavy))
            .tracking(1.5)
            .foregroundStyle(DauTheme.jade)
    }

    func questBody() -> some View {
        self.font(.system(.body, design: .rounded))
            .foregroundStyle(.primary)
            .fixedSize(horizontal: false, vertical: true)
    }

    func questCaption() -> some View {
        self.font(.system(.footnote, design: .rounded))
            .foregroundStyle(DauTheme.inkSoft)
            .fixedSize(horizontal: false, vertical: true)
    }

    func questPrimaryButton(fill: Color = DauTheme.coral) -> some View {
        self.font(.system(.body, design: .rounded).weight(.bold))
            .foregroundStyle(Color.white)
            .padding(.horizontal, 19)
            .frame(maxWidth: .infinity, minHeight: 54)
            .background(fill, in: RoundedRectangle(cornerRadius: 17))
    }
}
