import Foundation

/// The two Vietnamese accents Dấu grades against.
public enum Accent: String, Codable, Sendable, CaseIterable, Hashable {
    case north
    case south

    /// Vietnamese name, as shown on the accent picker.
    public var label: String {
        switch self {
        case .north: "Bắc"
        case .south: "Nam"
        }
    }

    /// The city the picker uses to make the choice concrete.
    public var city: String {
        switch self {
        case .north: "Hà Nội"
        case .south: "Sài Gòn"
        }
    }

    /// Tones this accent distinguishes in speech. Southern hỏi and ngã merge, so a Southern
    /// speaker produces five spoken tones from six written marks.
    public var spokenToneCount: Int {
        switch self {
        case .north: 6
        case .south: 5
        }
    }
}
