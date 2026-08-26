import DauCore
import Foundation

/// Narrows the web app's authoring inventory into the resource the app bundles.
///
/// Dropped on the way through: `css_variable`, `art_concept`, `ascii_base` duplication in
/// targets, `target_generation` (a generation-time concern), and the stored `target_audio`
/// paths, which are re-derived from what is actually on disk. Keeping them would let the
/// manifest claim audio the bundle does not have.
enum BuildContent {
    static func run(repoRoot: String, outputDirectory: String) throws {
        let root = URL(fileURLWithPath: repoRoot, isDirectory: true)
        let inventoryURL = root.appending(path: "api/data/inventory.json")
        let raw = try JSONSerialization.jsonObject(
            with: Data(contentsOf: inventoryURL)
        ) as? [String: Any] ?? [:]

        let tones = try toneInfos(from: raw)
        let (words, missing) = try wordEntries(from: raw, root: root)

        let content = DauContent(
            schemaVersion: DauContent.currentSchemaVersion,
            locale: raw["locale"] as? String ?? "vi-VN",
            defaultAccent: Accent(rawValue: raw["default_accent"] as? String ?? "north") ?? .north,
            tones: tones,
            words: words,
            minimalPairGroups: pairGroups(from: raw),
            themedDrills: drills(from: raw),
            featuredQueue: raw["featured_queue"] as? [String] ?? [],
            phrases: phrases(root: root)
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(content)

        let outputURL = URL(fileURLWithPath: outputDirectory, isDirectory: true)
        try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
        let destination = outputURL.appending(path: "dau-content-v1.json")
        try data.write(to: destination, options: Data.WritingOptions.atomic)

        print("wrote \(destination.path) — \(words.count) words, \(tones.count) tones, \(content.phrases.count) phrases, \(data.count / 1024) KB")
        // Missing references are expected for exactly two Southern words. Anything else is a
        // build error, because it means the audio pipeline silently lost a file.
        let expected: Set<String> = ["south/ma-grave", "south/phuong-phoenix"]
        let unexpected = missing.subtracting(expected)
        for entry in missing.sorted() {
            print("  no reference audio: \(entry)\(expected.contains(entry) ? " (known, generation failed)" : "")")
        }
        guard unexpected.isEmpty else {
            FileHandle.standardError.write(Data(
                "dau-tool: unexpected missing references: \(unexpected.sorted())\n".utf8
            ))
            exit(1)
        }
    }

    /// Phrases are authored iOS-side (`ios/content/phrases.json`) because the web app has
    /// its own dialogue scenes. Absent file means no captions content, not a build failure.
    private static func phrases(root: URL) -> [Phrase] {
        let url = root.appending(path: "ios/content/phrases.json")
        guard let data = try? Data(contentsOf: url),
              let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let entries = raw["phrases"] as? [[String: Any]] else { return [] }
        return entries.compactMap { entry in
            guard let id = entry["id"] as? String,
                  let text = entry["text"] as? String else { return nil }
            return Phrase(
                id: id, text: text,
                gloss: entry["gloss"] as? String ?? "",
                wordIDs: entry["word_ids"] as? [String] ?? []
            )
        }
    }

    private static func toneInfos(from raw: [String: Any]) throws -> [DauContent.ToneInfo] {
        (raw["tones"] as? [[String: Any]] ?? []).compactMap { entry in
            guard let id = entry["id"] as? String, let mark = ToneMark(rawValue: id) else { return nil }
            return DauContent.ToneInfo(
                id: mark,
                nameVi: entry["name_vi"] as? String ?? mark.label,
                nameEn: entry["name_en"] as? String ?? mark.hint,
                markEn: entry["mark_en"] as? String ?? "",
                color: entry["color"] as? String ?? "#FFFFFF",
                physicalCue: entry["physical_cue"] as? String ?? ""
            )
        }
    }

    private static func wordEntries(
        from raw: [String: Any], root: URL
    ) throws -> ([DauContent.Word], Set<String>) {
        var missing: Set<String> = []
        let words: [DauContent.Word] = (raw["words"] as? [[String: Any]] ?? []).compactMap { entry in
            guard let id = entry["id"] as? String,
                  let toneRaw = entry["tone"] as? String,
                  let tone = ToneMark(rawValue: toneRaw) else { return nil }

            // Derive reference availability from the filesystem, not from the manifest.
            var accents: [Accent] = []
            for accent in Accent.allCases {
                let wav = root.appending(path: "targets/\(accent.rawValue)/\(id).wav")
                if FileManager.default.fileExists(atPath: wav.path) {
                    accents.append(accent)
                } else {
                    missing.insert("\(accent.rawValue)/\(id)")
                }
            }
            return DauContent.Word(
                id: id,
                syllable: entry["syllable"] as? String ?? "",
                asciiBase: entry["ascii_base"] as? String ?? "",
                tone: tone,
                meaningEn: entry["meaning_en"] as? String ?? "",
                alternateMeaningsEn: entry["alternate_meanings_en"] as? [String] ?? [],
                usageNote: entry["usage_note"] as? String ?? "",
                minimalPairGroup: entry["minimal_pair_group"] as? String,
                minimalPairIDs: entry["minimal_pair_ids"] as? [String] ?? [],
                referenceAccents: accents
            )
        }
        return (words, missing)
    }

    /// Accepts either spelling of a group.
    ///
    /// `inventory.json` briefly carried two `minimal_pair_groups` keys with different
    /// schemas — `label`/`word_ids` and `title`/`forms`. Python's json takes the last
    /// duplicate and Apple's JSONSerialization takes the first, so the two consumers silently
    /// read different data and the Swift side produced groups with no words in them. The
    /// duplicate is gone, but reading both spellings costs nothing and means a future drift
    /// degrades instead of emptying the six-ma grid.
    private static func pairGroups(from raw: [String: Any]) -> [DauContent.MinimalPairGroup] {
        (raw["minimal_pair_groups"] as? [[String: Any]] ?? []).compactMap { entry in
            guard let id = entry["id"] as? String else { return nil }
            let forms = entry["forms"] as? [[String: Any]] ?? []
            let wordIDs = forms.isEmpty
                ? (entry["word_ids"] as? [String] ?? [])
                : forms.compactMap { $0["word_id"] as? String }
            let title = (entry["title"] as? String) ?? (entry["label"] as? String) ?? ""
            guard !wordIDs.isEmpty else {
                FileHandle.standardError.write(Data(
                    "dau-tool: minimal pair group '\(id)' has no words — schema drift?\n".utf8
                ))
                return nil
            }
            return DauContent.MinimalPairGroup(
                id: id,
                asciiBase: entry["ascii_base"] as? String ?? "",
                title: title,
                wordIDs: wordIDs
            )
        }
    }

    private static func drills(from raw: [String: Any]) -> [DauContent.ThemedDrill] {
        (raw["themed_drills"] as? [[String: Any]] ?? []).compactMap { entry in
            guard let id = entry["id"] as? String else { return nil }
            return DauContent.ThemedDrill(
                id: id,
                title: entry["title"] as? String ?? "",
                description: entry["description"] as? String ?? "",
                wordIDs: entry["word_ids"] as? [String] ?? []
            )
        }
    }
}
