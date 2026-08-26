import DauCore
import SwiftUI

/// Design tokens from the Dấu iOS v1 canvas (`Dau iOS v1.dc.html`).
///
/// The app is dark-only by design (`UIUserInterfaceStyle: Dark` in project.yml), so these are
/// literal values rather than an asset-catalog light/dark pair.
public enum DauTheme {
    /// Page ground.
    public static let ground = Color(hex: 0x0F0D0A)
    /// The darker ground behind the device frame / launch screen.
    public static let groundDeep = Color(hex: 0x0B0A08)
    /// Raised card.
    public static let card = Color(hex: 0x1A1712)
    /// Recessed well — the pitch-trace lane.
    public static let well = Color(hex: 0x14110D)
    /// Primary action + brand.
    public static let coral = Color(hex: 0xFF6B5E)
    /// Text on a coral fill.
    public static let onCoral = Color(hex: 0x1B100D)
    /// Primary text.
    public static let cream = Color(hex: 0xF6EEDF)
    /// Secondary text.
    public static let muted = Color(hex: 0xB6AC9A)
    /// Tertiary text and captions.
    public static let faint = Color(hex: 0x8F8776)
    /// Verified / matched.
    public static let verified = Color(hex: 0x35C1B4)
    /// Didn't match.
    public static let missed = Color(hex: 0xFF5A4A)

    public static let hairline = Color.white.opacity(0.08)
}

public extension DauTheme {
    /// Per-tone colours, taken from the design canvas.
    ///
    /// Four of the six match `api/data/inventory.json` exactly; huyền and hỏi were lightened
    /// for the dark ground (`#4D72C9 -> #5F86DF`, `#9B7AE8 -> #A98AF4`). The canvas values
    /// win — the app renders on the dark ground, not the web app's light one.
    static func toneColor(_ tone: ToneMark) -> Color {
        switch tone {
        case .ngang: Color(hex: 0xD8C7A0)
        case .huyen: Color(hex: 0x5F86DF)
        case .sac: Color(hex: 0xFF6B5E)
        case .hoi: Color(hex: 0xA98AF4)
        case .nga: Color(hex: 0x35C1B4)
        case .nang: Color(hex: 0xF4A641)
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
