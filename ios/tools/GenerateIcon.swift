// Placeholder app icon for Dấu. Regenerate with:
//   swiftc -parse-as-library tools/GenerateIcon.swift -o /tmp/dauicon
//   /tmp/dauicon Resources/Assets.xcassets/AppIcon.appiconset/AppIcon.png
// Canonical source: maple-hollow/templates/swift/GenerateIcon.swift
// Reference implementations: maple-springs/tools/GenerateIcon.swift,
//   prototypes/bento-brigade/tools/GenerateIcon.swift
//
// Placeholder for the scaffold stage — a real icon pass (toolbench `icon-gen`)
// replaces this before TestFlight. Draws the brand mark: the dấu sắc rising
// contour on the app's dark ground. CoreGraphics only, no app dependencies.
// Note the fleet's flat-2D cozy art bar is a *game* rule; Dấu owns its own look.

import CoreGraphics
import Foundation
import ImageIO
import UniformTypeIdentifiers

@main
enum GenerateIcon {
    static func main() {
        let size = 1024
        let out = CommandLine.arguments.count > 1
            ? CommandLine.arguments[1]
            : "AppIcon.png"

        let space = CGColorSpaceCreateDeviceRGB()
        guard let ctx = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
                                  bytesPerRow: 0, space: space,
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else {
            fatalError("no context")
        }
        let s = CGFloat(size)

        func color(_ r: Double, _ g: Double, _ b: Double, _ a: Double = 1) -> CGColor {
            CGColor(colorSpace: space, components: [CGFloat(r), CGFloat(g), CGFloat(b), CGFloat(a)])!
        }

        // ---- Dấu placeholder: the rising sắc contour on the app ground. -----
        ctx.setFillColor(color(0.059, 0.051, 0.039))   // #0F0D0A
        ctx.fill(CGRect(x: 0, y: 0, width: s, height: s))

        // Coral glow behind the stroke.
        let glow = CGGradient(colorsSpace: space,
                              colors: [color(1.0, 0.42, 0.37, 0.22), color(1.0, 0.42, 0.37, 0)] as CFArray,
                              locations: [0, 1])!
        ctx.drawRadialGradient(glow, startCenter: CGPoint(x: s * 0.5, y: s * 0.5), startRadius: 0,
                               endCenter: CGPoint(x: s * 0.5, y: s * 0.5), endRadius: s * 0.5, options: [])

        // Three staff lines, as on the practice trace.
        ctx.setStrokeColor(color(0.94, 0.93, 0.87, 0.10))
        ctx.setLineWidth(s * 0.008)
        for fraction in [0.34, 0.5, 0.66] {
            ctx.move(to: CGPoint(x: s * 0.18, y: s * fraction))
            ctx.addLine(to: CGPoint(x: s * 0.82, y: s * fraction))
        }
        ctx.strokePath()

        // The rising contour — dấu sắc, the tone the cold-open teaches.
        ctx.setStrokeColor(color(1.0, 0.42, 0.37))     // #FF6B5E
        ctx.setLineWidth(s * 0.075)
        ctx.setLineCap(.round)
        ctx.move(to: CGPoint(x: s * 0.22, y: s * 0.30))
        ctx.addCurve(to: CGPoint(x: s * 0.78, y: s * 0.72),
                     control1: CGPoint(x: s * 0.46, y: s * 0.31),
                     control2: CGPoint(x: s * 0.58, y: s * 0.52))
        ctx.strokePath()
        // ---- End replaceable drawing. ------------------------------------

        guard let image = ctx.makeImage() else { fatalError("no image") }
        let url = URL(fileURLWithPath: out)
        guard let dest = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            fatalError("no destination")
        }
        CGImageDestinationAddImage(dest, image, nil)
        CGImageDestinationFinalize(dest)
        print("wrote \(out)")
    }
}
