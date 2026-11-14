import CoreGraphics
import Foundation
let wanted = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
let list = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
for w in list {
    let owner = w[kCGWindowOwnerName as String] as? String ?? ""
    if !wanted.isEmpty && owner != wanted { continue }
    let id = w[kCGWindowNumber as String] as? Int ?? 0
    let layer = w[kCGWindowLayer as String] as? Int ?? 0
    let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let width = b["Width"] as? Double ?? 0, height = b["Height"] as? Double ?? 0
    if layer != 0 || width < 200 || height < 200 { continue }
    print("\(id)\t\(owner)\t\(Int(width))x\(Int(height))")
}
