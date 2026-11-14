// Reads the text in an image with macOS's built-in recogniser and prints one JSON
// object per line: {"text", "x", "y", "w", "h", "conf"}, with coordinates as
// fractions of the image and y measured from the top.
//
// Build:  swiftc -O -o .cache/ocr rivals/screen/ocr.swift
// Use:    .cache/ocr image.png [fast]
import AppKit
import Foundation
import Vision

let args = CommandLine.arguments
guard args.count >= 2, let image = NSImage(contentsOfFile: args[1]),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    FileHandle.standardError.write("usage: ocr image.png [fast]\n".data(using: .utf8)!)
    exit(2)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = (args.count > 2 && args[2] == "fast") ? .fast : .accurate
request.usesLanguageCorrection = false
request.minimumTextHeight = 0.008
try VNImageRequestHandler(cgImage: cg, options: [:]).perform([request])
for observation in request.results ?? [] {
    guard let best = observation.topCandidates(1).first else { continue }
    let box = observation.boundingBox
    let item: [String: Any] = [
        "text": best.string,
        "x": Double(box.minX), "y": Double(1 - box.maxY),
        "w": Double(box.width), "h": Double(box.height),
        "conf": Double(best.confidence),
    ]
    let data = try JSONSerialization.data(withJSONObject: item, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}
