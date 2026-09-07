import Foundation

enum CafeLessonStep: Int, CaseIterable, Identifiable {
    case welcome, prepare, observe, listen, request, repair, changedOrder, finish

    var id: Int { rawValue }
    var title: String {
        switch self {
        case .welcome: "Your café mission"
        case .prepare: "Meet the menu"
        case .observe: "Watch an order"
        case .listen: "What did she ask?"
        case .request: "Ask for a drink"
        case .repair: "When you need another listen"
        case .changedOrder: "The café is out of coffee"
        case .finish: "Mission complete"
        }
    }
}
