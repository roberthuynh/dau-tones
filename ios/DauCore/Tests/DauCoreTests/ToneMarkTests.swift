import Testing
@testable import DauCore

@Suite("ToneMark")
struct ToneMarkTests {
    @Test("detects each of the six marks on the canonical ma set")
    func detectsSixTones() {
        #expect(ToneMark.of("ma") == .ngang)
        #expect(ToneMark.of("mà") == .huyen)
        #expect(ToneMark.of("má") == .sac)
        #expect(ToneMark.of("mả") == .hoi)
        #expect(ToneMark.of("mã") == .nga)
        #expect(ToneMark.of("mạ") == .nang)
    }

    @Test("vowel-quality marks are not tones")
    func qualityMarksAreNotTones() {
        // Circumflex, breve and horn decompose to combining scalars too; only the five
        // tone scalars count, and a bare quality-marked vowel is ngang.
        #expect(ToneMark.of("cơm") == .ngang)
        #expect(ToneMark.of("ăn") == .ngang)
        #expect(ToneMark.of("tôi") == .ngang)
        // ...and they coexist with a real tone mark without confusing detection.
        #expect(ToneMark.of("phở") == .hoi)
        #expect(ToneMark.of("về") == .huyen)
        #expect(ToneMark.of("phường") == .huyen)
        #expect(ToneMark.of("mũ") == .nga)
    }

    @Test("stripping removes the tone but keeps vowel quality")
    func strippingKeepsVowelQuality() {
        #expect(ToneMark.stripped(from: "phở") == "phơ")
        #expect(ToneMark.stripped(from: "mã") == "ma")
        #expect(ToneMark.stripped(from: "phường") == "phương")
        #expect(ToneMark.stripped(from: "cửa") == "cưa")
        #expect(ToneMark.stripped(from: "ăn") == "ăn")
    }

    /// The Phase B caption rule: recognition supplies the word, the DSP supplies the tone.
    /// Robert's own receipts show gpt-4o-transcribe writing `mả` as `mã`; Apple's recognizer
    /// normalizes too. Without this the caption confidently shows a tone nobody said.
    @Test("re-applies the measured tone over whatever ASR wrote")
    func reappliesMeasuredTone() {
        #expect(ToneMark.applying(.hoi, to: "mã") == "mả")
        #expect(ToneMark.applying(.ngang, to: "mã") == "ma")
        #expect(ToneMark.applying(.nang, to: "ma") == "mạ")
        #expect(ToneMark.applying(.sac, to: "mà") == "má")
        #expect(ToneMark.applying(.huyen, to: "phở") == "phờ")
        #expect(ToneMark.applying(.sac, to: "phương") == "phướng")
        #expect(ToneMark.applying(.huyen, to: "cưa") == "cừa")
    }

    /// Vietnamese does not simply mark the last vowel. These are the cases that break a
    /// naive implementation — the first one shipped as `cưà` before this test existed.
    @Test("mark placement follows Vietnamese orthography")
    func orthographicPlacement() {
        // Open syllable, two vowels -> penultimate.
        #expect(ToneMark.applying(.huyen, to: "cưa") == "cừa")
        #expect(ToneMark.applying(.huyen, to: "mua") == "mùa")
        #expect(ToneMark.applying(.huyen, to: "kia") == "kìa")
        // ...except the glide onsets oa / oe / uy, which mark the last.
        #expect(ToneMark.applying(.huyen, to: "hoa") == "hoà")
        #expect(ToneMark.applying(.hoi, to: "khoe") == "khoẻ")
        #expect(ToneMark.applying(.sac, to: "thuy") == "thuý")
        // ê / ô / ơ outrank everything.
        #expect(ToneMark.applying(.sac, to: "tieng") == "tiéng")
        #expect(ToneMark.applying(.sac, to: "tiêng") == "tiếng")
        #expect(ToneMark.applying(.nang, to: "được") == "được")
        // A closing consonant pins the mark to the last nucleus vowel.
        #expect(ToneMark.applying(.sac, to: "toan") == "toán")
        #expect(ToneMark.applying(.nang, to: "ban") == "bạn")
    }

    @Test("applying every tone round-trips through detection")
    func applyingRoundTrips() {
        for base in ["ma", "phơ", "cưa", "ăn", "tôi", "phương", "mu"] {
            for tone in ToneMark.allCases {
                let written = ToneMark.applying(tone, to: base)
                #expect(
                    ToneMark.of(written) == tone,
                    "\(base) + \(tone.rawValue) wrote '\(written)'"
                )
                #expect(ToneMark.stripped(from: written) == base)
            }
        }
    }
}

@Suite("ToneFamily")
struct ToneFamilyTests {
    @Test("six tones collapse to four families per accent")
    func familyMapping() {
        #expect(ToneMark.ngang.family(in: .north) == .level)
        #expect(ToneMark.sac.family(in: .north) == .rising)
        #expect(ToneMark.huyen.family(in: .north) == .falling)
        #expect(ToneMark.nang.family(in: .north) == .falling)
        #expect(ToneMark.hoi.family(in: .north) == .dipping)
        // The one accent-dependent row: Northern ngã rides with rising sắc, Southern ngã
        // merges into dipping with hỏi.
        #expect(ToneMark.nga.family(in: .north) == .rising)
        #expect(ToneMark.nga.family(in: .south) == .dipping)
    }

    /// The honesty gate for "You said ma — ghost". Naming a word the learner did not mean is
    /// only defensible where the produced family resolves to exactly one tone.
    @Test("only uniquely-resolving families may name a tone")
    func unambiguousResolution() {
        // Level resolves in both accents — which is why the cold-open ma/má pair works.
        #expect(ToneFamily.level.unambiguousTone(in: .north) == .ngang)
        #expect(ToneFamily.level.unambiguousTone(in: .south) == .ngang)
        // Rising resolves only in the South; in the North sắc and ngã share it.
        #expect(ToneFamily.rising.unambiguousTone(in: .south) == .sac)
        #expect(ToneFamily.rising.unambiguousTone(in: .north) == nil)
        // Dipping resolves only in the North; Southern hỏi/ngã are genuinely one spoken tone.
        #expect(ToneFamily.dipping.unambiguousTone(in: .north) == .hoi)
        #expect(ToneFamily.dipping.unambiguousTone(in: .south) == nil)
        // Falling never resolves: huyền and nặng differ by duration and final energy.
        #expect(ToneFamily.falling.unambiguousTone(in: .north) == nil)
        #expect(ToneFamily.falling.unambiguousTone(in: .south) == nil)
    }

    @Test("Southern speech distinguishes five tones, Northern six")
    func spokenToneCounts() {
        let north = Set(ToneMark.allCases.map { $0.family(in: .north) })
        let south = Set(ToneMark.allCases.map { $0.family(in: .south) })
        #expect(north.count == 4)
        #expect(south.count == 4)
        #expect(Accent.north.spokenToneCount == 6)
        #expect(Accent.south.spokenToneCount == 5)
    }
}
