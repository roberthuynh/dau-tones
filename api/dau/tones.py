"""Deterministic Vietnamese tone analysis.

The pitch tracker measures. The language model coaches. This module deliberately
contains no language-model calls and never uses the learner's intended tone to
influence detection.
"""

from __future__ import annotations

import io
import math
import unicodedata
import wave
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO, cast

import numpy as np

SAMPLE_RATE = 22_050
FRAME_LENGTH = 1_024
HOP_LENGTH = 256
F0_MIN_HZ = 65.0
F0_MAX_HZ = 650.0
CONTOUR_POINTS = 64


class Tone(StrEnum):
    NGANG = "ngang"
    HUYEN = "huyen"
    SAC = "sac"
    HOI = "hoi"
    NGA = "nga"
    NANG = "nang"


TONE_ORDER: tuple[Tone, ...] = (
    Tone.NGANG,
    Tone.HUYEN,
    Tone.SAC,
    Tone.HOI,
    Tone.NGA,
    Tone.NANG,
)

TONE_LABELS: dict[Tone, str] = {
    Tone.NGANG: "ngang",
    Tone.HUYEN: "huyền",
    Tone.SAC: "sắc",
    Tone.HOI: "hỏi",
    Tone.NGA: "ngã",
    Tone.NANG: "nặng",
}

_TONE_ALIASES = {
    "ngang": Tone.NGANG,
    "level": Tone.NGANG,
    "huyen": Tone.HUYEN,
    "huyền": Tone.HUYEN,
    "falling": Tone.HUYEN,
    "sac": Tone.SAC,
    "sắc": Tone.SAC,
    "rising": Tone.SAC,
    "hoi": Tone.HOI,
    "hỏi": Tone.HOI,
    "dipping": Tone.HOI,
    "nga": Tone.NGA,
    "ngã": Tone.NGA,
    "broken": Tone.NGA,
    "nang": Tone.NANG,
    "nặng": Tone.NANG,
    "heavy": Tone.NANG,
}


class Accent(StrEnum):
    NORTH = "north"
    SOUTH = "south"


_ACCENT_ALIASES = {
    "north": Accent.NORTH,
    "northern": Accent.NORTH,
    "ha noi": Accent.NORTH,
    "hanoi": Accent.NORTH,
    "hà nội": Accent.NORTH,
    "south": Accent.SOUTH,
    "southern": Accent.SOUTH,
    "sai gon": Accent.SOUTH,
    "saigon": Accent.SOUTH,
    "sài gòn": Accent.SOUTH,
}


class ToneFamily(StrEnum):
    LEVEL = "level"
    FALLING = "falling"
    RISING = "rising"
    DIPPING = "dipping"


FAMILY_ORDER: tuple[ToneFamily, ...] = (
    ToneFamily.LEVEL,
    ToneFamily.FALLING,
    ToneFamily.RISING,
    ToneFamily.DIPPING,
)


class ScoringMode(StrEnum):
    SIX_TONE = "six-tone"
    FOUR_FAMILY = "four-family"


class SignalQualityCode(StrEnum):
    DECODE_FAILED = "decode_failed"
    SILENCE = "silence"
    CLIPPED = "clipped"
    TOO_SHORT = "too_short"
    TOO_LONG = "too_long"
    MULTIPLE_UTTERANCES = "multiple_utterances"
    INSUFFICIENT_VOICING = "insufficient_voicing"
    VOICING_GAP = "voicing_gap"
    NO_PITCH = "no_pitch"
    NONFINITE_AUDIO = "nonfinite_audio"


class SignalQualityError(ValueError):
    """A learner-facing, machine-readable audio rejection."""

    def __init__(
        self,
        code: SignalQualityCode,
        message: str,
        *,
        details: Mapping[str, float | int | str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True)
class SignalQuality:
    peak: float
    rms: float
    clipping_fraction: float
    active_duration_s: float
    total_duration_s: float
    voiced_fraction: float = 0.0
    longest_voicing_gap_ms: float = 0.0
    island_count: int = 1


@dataclass(frozen=True)
class ContourFeatures:
    start: float
    end: float
    slope: float
    curvature: float
    pitch_range: float
    minimum: float
    dip_position: float
    recovery: float
    final_rise: float
    duration_s: float
    voiced_fraction: float
    longest_voicing_gap_ms: float
    central_rms_dip: float
    terminal_energy_drop: float

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ContourFeatures:
        defaults = {
            "start": 0.0,
            "end": 0.0,
            "slope": 0.0,
            "curvature": 0.0,
            "pitch_range": 0.0,
            "minimum": 0.0,
            "dip_position": 0.5,
            "recovery": 0.0,
            "final_rise": 0.0,
            "duration_s": 0.5,
            "voiced_fraction": 1.0,
            "longest_voicing_gap_ms": 0.0,
            "central_rms_dip": 0.0,
            "terminal_energy_drop": 0.0,
        }
        return cls(**{key: float(value.get(key, default)) for key, default in defaults.items()})

    def as_dict(self) -> dict[str, float]:
        return {key: float(value) for key, value in asdict(self).items()}


@dataclass(frozen=True)
class PitchContour:
    points: np.ndarray
    features: ContourFeatures
    quality: SignalQuality
    raw_f0_hz: np.ndarray = field(repr=False)
    raw_voiced: np.ndarray = field(repr=False)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contour": [round(float(point), 5) for point in self.points],
            "features": self.features.as_dict(),
            "quality": asdict(self.quality),
        }


@dataclass(frozen=True)
class ToneTemplate:
    id: str
    word: str
    tone: Tone
    accent: Accent
    contour: np.ndarray
    features: ContourFeatures
    source_path: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ToneTemplate:
        contour = np.asarray(value.get("contour", value.get("points", [])), dtype=np.float64)
        if contour.size != CONTOUR_POINTS:
            contour = resample_contour(contour, CONTOUR_POINTS)
        features_value = value.get("features")
        features = (
            ContourFeatures.from_mapping(features_value)
            if isinstance(features_value, Mapping)
            else extract_features(contour)
        )
        return cls(
            id=str(value.get("id", value.get("target_id", value.get("word", "target")))),
            word=str(value.get("word", value.get("syllable", ""))),
            tone=canonical_tone(value.get("tone", "ngang")),
            accent=canonical_accent(value.get("accent", "north")),
            contour=contour,
            features=features,
            source_path=str(value["path"]) if value.get("path") else None,
        )


@dataclass(frozen=True)
class ToneAlternative:
    tone: Tone
    family: ToneFamily
    score: float
    probability: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "tone": self.tone.value,
            "family": self.family.value,
            "score": round(self.score, 6),
            "probability": round(self.probability, 6),
        }


@dataclass(frozen=True)
class ClassificationResult:
    tone: Tone
    family: ToneFamily
    confidence: float
    scoring_mode: ScoringMode
    exact_verified: bool
    needs_retry: bool
    alternatives: tuple[ToneAlternative, ...]
    scores: Mapping[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "tone_detected": self.tone.value,
            "family_detected": self.family.value,
            "confidence": round(self.confidence, 6),
            "grading_mode": self.scoring_mode.value,
            "exact_verified": self.exact_verified,
            "needs_retry": self.needs_retry,
            "alternatives": [alternative.as_dict() for alternative in self.alternatives],
            "scores": {key: round(float(value), 6) for key, value in self.scores.items()},
        }


@dataclass(frozen=True)
class CandidateValidation:
    passed: bool
    tone: Tone
    accent: Accent
    shape_score: float
    separation_margin: float
    reason_codes: tuple[str, ...]
    contour: PitchContour | None = field(default=None, repr=False)
    accent_family_verified: bool = False

    def as_dict(self) -> dict[str, Any]:
        shape_score = round(self.shape_score, 6) if math.isfinite(self.shape_score) else None
        separation_margin = (
            round(self.separation_margin, 6) if math.isfinite(self.separation_margin) else None
        )
        result: dict[str, Any] = {
            "passed": self.passed,
            "tone": self.tone.value,
            "accent": self.accent.value,
            "shape_score": shape_score,
            "separation_margin": separation_margin,
            "reason_codes": list(self.reason_codes),
            "accent_family_verified": self.accent_family_verified,
        }
        if self.contour is not None:
            result.update(self.contour.as_dict())
        return result


def _strip_accents(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", value.lower().strip())
        if unicodedata.category(character) != "Mn"
    ).replace("đ", "d")


def canonical_tone(value: Tone | str) -> Tone:
    if isinstance(value, Tone):
        return value
    raw = str(value).lower().strip()
    tone = _TONE_ALIASES.get(raw) or _TONE_ALIASES.get(_strip_accents(raw))
    if tone is None:
        raise ValueError(f"Unknown Vietnamese tone: {value!r}")
    return tone


def canonical_accent(value: Accent | str) -> Accent:
    if isinstance(value, Accent):
        return value
    raw = str(value).lower().strip()
    accent = _ACCENT_ALIASES.get(raw) or _ACCENT_ALIASES.get(_strip_accents(raw))
    if accent is None:
        raise ValueError(f"Unknown Vietnamese accent: {value!r}")
    return accent


def tone_family(tone: Tone | str, accent: Accent | str = Accent.NORTH) -> ToneFamily:
    """Map six orthographic tones to four pitch-observable families.

    Northern ngã is grouped with rising sắc when exact glottal cues are not
    conclusive. In common Southern speech hỏi and ngã merge, so they share the
    dipping family.
    """

    resolved_tone = canonical_tone(tone)
    resolved_accent = canonical_accent(accent)
    if resolved_tone is Tone.NGANG:
        return ToneFamily.LEVEL
    if resolved_tone in (Tone.HUYEN, Tone.NANG):
        return ToneFamily.FALLING
    if resolved_tone is Tone.SAC:
        return ToneFamily.RISING
    if resolved_tone is Tone.NGA:
        return ToneFamily.DIPPING if resolved_accent is Accent.SOUTH else ToneFamily.RISING
    return ToneFamily.DIPPING


def _pcm_bytes_to_float(data: bytes, sample_width: int, channels: int) -> np.ndarray:
    if sample_width == 1:
        samples = (np.frombuffer(data, dtype=np.uint8).astype(np.float64) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(data, dtype="<i2").astype(np.float64) / 32768.0
    elif sample_width == 3:
        raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
        values = (
            raw[:, 0].astype(np.int32)
            | (raw[:, 1].astype(np.int32) << 8)
            | (raw[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        samples = values.astype(np.float64) / 8_388_608.0
    elif sample_width == 4:
        samples = np.frombuffer(data, dtype="<i4").astype(np.float64) / 2_147_483_648.0
    else:
        raise SignalQualityError(
            SignalQualityCode.DECODE_FAILED,
            f"Unsupported WAV sample width: {sample_width}",
        )
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples.astype(np.float32)


def _decode_wave(
    source: str | Path | bytes | bytearray | BinaryIO,
) -> tuple[np.ndarray, int]:
    stream: Any
    if isinstance(source, (bytes, bytearray)):
        stream = io.BytesIO(bytes(source))
    elif isinstance(source, Path):
        # Python 3.11's wave.open treats Path as an already-open stream.
        stream = str(source)
    else:
        stream = source
    try:
        with wave.open(stream, "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            sample_width = wav.getsampwidth()
            data = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError, OSError) as error:
        raise SignalQualityError(
            SignalQualityCode.DECODE_FAILED,
            "That audio file could not be decoded. Try recording again.",
            details={"decoder": "wave", "error": str(error)},
        ) from error
    return _pcm_bytes_to_float(data, sample_width, channels), sample_rate


def _decode_av(
    source: str | Path | bytes | bytearray | BinaryIO,
) -> tuple[np.ndarray, int]:
    try:
        import av
    except ImportError as error:
        raise SignalQualityError(
            SignalQualityCode.DECODE_FAILED,
            "PyAV is not installed and this recording is not a PCM WAV.",
            details={"decoder": "pyav_unavailable"},
        ) from error

    container_source: Any = (
        io.BytesIO(bytes(source)) if isinstance(source, (bytes, bytearray)) else source
    )
    chunks: list[np.ndarray] = []
    try:
        with av.open(container_source, mode="r") as container:
            audio_stream = next(
                (stream for stream in container.streams if stream.type == "audio"), None
            )
            if audio_stream is None:
                raise ValueError("No audio stream")
            resampler = av.audio.resampler.AudioResampler(
                format="fltp",
                layout="mono",
                rate=SAMPLE_RATE,
            )
            for frame in container.decode(audio_stream):
                converted = resampler.resample(frame)
                if converted is None:
                    continue
                frames = converted if isinstance(converted, list) else [converted]
                for converted_frame in frames:
                    array = np.asarray(converted_frame.to_ndarray(), dtype=np.float32)
                    chunks.append(array.reshape(-1))
            flushed = resampler.resample(None)
            if flushed is not None:
                frames = flushed if isinstance(flushed, list) else [flushed]
                for converted_frame in frames:
                    chunks.append(
                        np.asarray(converted_frame.to_ndarray(), dtype=np.float32).reshape(-1)
                    )
    except Exception as error:
        raise SignalQualityError(
            SignalQualityCode.DECODE_FAILED,
            "That audio file could not be decoded. Try recording again.",
            details={"decoder": "pyav", "error": str(error)},
        ) from error
    if not chunks:
        raise SignalQualityError(
            SignalQualityCode.DECODE_FAILED,
            "The recording did not contain an audio track.",
            details={"decoder": "pyav"},
        )
    return np.concatenate(chunks), SAMPLE_RATE


def decode_audio(
    source: str | Path | bytes | bytearray | BinaryIO,
) -> tuple[np.ndarray, int]:
    """Decode WAV, WebM/Opus, MP4/AAC, or Ogg audio without shelling out."""

    # The committed targets and no-mic demos are PCM WAV files. Recognize them
    # before importing PyAV so the demo path does not pay for a native codec
    # stack that Python's standard library can decode directly. Browser formats
    # still take the same PyAV path below.
    is_wave_bytes = (
        isinstance(source, (bytes, bytearray))
        and bytes(source[:12]).startswith(b"RIFF")
        and bytes(source[8:12]) == b"WAVE"
    )
    is_wave_path = isinstance(source, (str, Path)) and Path(source).suffix.lower() == ".wav"
    if is_wave_bytes or is_wave_path:
        return _decode_wave(source)

    try:
        return _decode_av(source)
    except SignalQualityError as av_error:
        try:
            return _decode_wave(source)
        except SignalQualityError:
            raise av_error from None


def _resample_audio(samples: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return samples.astype(np.float32, copy=False)
    try:
        from .librosa_compat import librosa

        return np.asarray(
            librosa.resample(
                samples.astype(np.float64), orig_sr=source_rate, target_sr=target_rate
            ),
            dtype=np.float32,
        )
    except ImportError:
        try:
            from scipy.signal import resample_poly  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("Audio resampling needs librosa or scipy") from error
        divisor = math.gcd(source_rate, target_rate)
        return np.asarray(
            resample_poly(samples, target_rate // divisor, source_rate // divisor),
            dtype=np.float32,
        )


def _frame_rms(
    samples: np.ndarray, frame_length: int = FRAME_LENGTH, hop_length: int = HOP_LENGTH
) -> np.ndarray:
    if samples.size == 0:
        return np.zeros(0, dtype=np.float64)
    padded = np.pad(
        samples.astype(np.float64),
        (frame_length // 2, frame_length // 2),
        mode="constant",
    )
    starts = np.arange(0, max(1, padded.size - frame_length + 1), hop_length)
    return np.asarray(
        [math.sqrt(float(np.mean(padded[start : start + frame_length] ** 2))) for start in starts],
        dtype=np.float64,
    )


def _fill_short_false_runs(mask: np.ndarray, maximum_frames: int) -> np.ndarray:
    result = mask.copy()
    index = 0
    while index < result.size:
        if result[index]:
            index += 1
            continue
        end = index
        while end < result.size and not result[end]:
            end += 1
        if index > 0 and end < result.size and end - index <= maximum_frames:
            result[index:end] = True
        index = end
    return result


def _true_runs(mask: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, active in enumerate(mask):
        if active and start is None:
            start = index
        elif not active and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, mask.size))
    return runs


def isolate_primary_speech(
    samples: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    *,
    minimum_duration_s: float = 0.12,
    maximum_duration_s: float = 2.5,
) -> tuple[np.ndarray, SignalQuality]:
    """Validate a recording and return its single primary speech island."""

    waveform = np.asarray(samples, dtype=np.float64).reshape(-1)
    if waveform.size == 0 or not np.all(np.isfinite(waveform)):
        raise SignalQualityError(
            SignalQualityCode.NONFINITE_AUDIO,
            "The recording is empty or damaged. Try recording again.",
        )
    total_duration = waveform.size / sample_rate
    peak = float(np.max(np.abs(waveform)))
    overall_rms = float(math.sqrt(np.mean(waveform**2)))
    clipping_fraction = float(np.mean(np.abs(waveform) >= 0.995))
    if overall_rms < 0.0025 or peak < 0.01:
        raise SignalQualityError(
            SignalQualityCode.SILENCE,
            "I could not hear a voice. Move closer and try again.",
            details={"rms": overall_rms, "peak": peak},
        )
    if clipping_fraction > 0.02:
        raise SignalQualityError(
            SignalQualityCode.CLIPPED,
            "The recording is distorted. Move a little farther from the mic.",
            details={"clipping_fraction": clipping_fraction},
        )

    rms = _frame_rms(waveform)
    high = float(np.percentile(rms, 90)) if rms.size else 0.0
    quiet = float(np.percentile(rms, 20)) if rms.size else 0.0
    threshold = max(0.003, high * 0.16)
    if quiet < high * 0.35:
        threshold = max(threshold, min(high * 0.60, quiet * 2.5))
    active = rms >= threshold
    active = _fill_short_false_runs(active, max(1, round(0.08 * sample_rate / HOP_LENGTH)))
    minimum_island_frames = max(2, round(0.06 * sample_rate / HOP_LENGTH))
    runs = [run for run in _true_runs(active) if run[1] - run[0] >= minimum_island_frames]
    if not runs:
        raise SignalQualityError(
            SignalQualityCode.SILENCE,
            "I could not find a clear syllable. Try recording again.",
        )

    energies = [float(np.sum(rms[start:end] ** 2)) for start, end in runs]
    primary_index = int(np.argmax(energies))
    primary = runs[primary_index]
    substantial = [
        index
        for index, ((start, end), energy) in enumerate(zip(runs, energies, strict=True))
        if (end - start) * HOP_LENGTH / sample_rate >= 0.12
        and energy >= energies[primary_index] * 0.25
    ]
    if len(substantial) > 1:
        raise SignalQualityError(
            SignalQualityCode.MULTIPLE_UTTERANCES,
            "Say one word at a time, with a short pause before and after.",
            details={"island_count": len(substantial)},
        )

    start_frame, end_frame = primary
    active_duration = (end_frame - start_frame) * HOP_LENGTH / sample_rate
    if active_duration < minimum_duration_s:
        raise SignalQualityError(
            SignalQualityCode.TOO_SHORT,
            "That was too short to grade. Hold the vowel a little longer.",
            details={"active_duration_s": active_duration},
        )
    if active_duration > maximum_duration_s:
        raise SignalQualityError(
            SignalQualityCode.TOO_LONG,
            "Say just the target word, not a full phrase.",
            details={"active_duration_s": active_duration},
        )

    padding = round(0.05 * sample_rate)
    sample_start = max(0, start_frame * HOP_LENGTH - padding)
    sample_end = min(waveform.size, end_frame * HOP_LENGTH + FRAME_LENGTH + padding)
    segment = waveform[sample_start:sample_end]
    quality = SignalQuality(
        peak=peak,
        rms=overall_rms,
        clipping_fraction=clipping_fraction,
        active_duration_s=active_duration,
        total_duration_s=total_duration,
        island_count=len(substantial),
    )
    return segment.astype(np.float32), quality


def _longest_internal_gap(voiced: np.ndarray) -> tuple[int, float]:
    indices = np.flatnonzero(voiced)
    if indices.size < 2:
        return 0, 0.5
    internal = voiced[indices[0] : indices[-1] + 1]
    longest = 0
    longest_center = 0.5
    index = 0
    while index < internal.size:
        if internal[index]:
            index += 1
            continue
        end = index
        while end < internal.size and not internal[end]:
            end += 1
        length = end - index
        if length > longest:
            longest = length
            longest_center = (indices[0] + (index + end) / 2) / max(1, voiced.size - 1)
        index = end
    return longest, float(longest_center)


def _remove_octave_spikes(f0: np.ndarray) -> np.ndarray:
    corrected = np.asarray(f0, dtype=np.float64).copy()
    valid = np.flatnonzero(np.isfinite(corrected) & (corrected > 0))
    if valid.size < 3:
        return corrected
    semitones = 12.0 * np.log2(corrected[valid])
    for position in range(1, valid.size - 1):
        local_median = float(np.median(semitones[max(0, position - 2) : position + 3]))
        current = semitones[position]
        candidates = np.array([current - 12.0, current, current + 12.0])
        replacement = float(candidates[np.argmin(np.abs(candidates - local_median))])
        if abs(current - local_median) > 7.0 and abs(replacement - local_median) < 4.5:
            semitones[position] = replacement
    corrected[valid] = 2.0 ** (semitones / 12.0)
    return corrected


def _select_voiced_frames(
    f0: np.ndarray,
    voiced_flag: np.ndarray,
    voiced_probability: np.ndarray | None,
) -> np.ndarray:
    """Prefer high-confidence pYIN frames without discarding its decoded track.

    ``librosa.pyin`` already applies Viterbi decoding to produce ``voiced_flag``.
    Its independent per-frame probability can remain low for breathy or
    glottalized Vietnamese vowels even when the decoded pitch track is coherent.
    Keep the stricter mask when it has enough coverage, then fall back to the
    decoded mask so that probability is not treated as a second voicing verdict.
    """

    decoded = np.asarray(voiced_flag, dtype=bool) & np.isfinite(f0) & (f0 > 0)
    if voiced_probability is None:
        return cast(np.ndarray, decoded)
    probability = np.asarray(voiced_probability, dtype=np.float64)
    confident = decoded & (np.nan_to_num(probability, nan=0.0) >= 0.35)
    confident_fraction = float(np.mean(confident)) if confident.size else 0.0
    if int(np.sum(confident)) >= 5 and confident_fraction >= 0.32:
        return cast(np.ndarray, confident)
    return cast(np.ndarray, decoded)


def _smooth(values: np.ndarray) -> np.ndarray:
    if values.size < 5:
        return values.copy()
    window = min(11, values.size if values.size % 2 else values.size - 1)
    window = max(5, window)
    try:
        from scipy.signal import savgol_filter

        return np.asarray(savgol_filter(values, window_length=window, polyorder=2, mode="interp"))
    except ImportError:
        kernel_size = min(5, values.size)
        kernel = np.ones(kernel_size) / kernel_size
        padded = np.pad(values, (kernel_size // 2, kernel_size - 1 - kernel_size // 2), mode="edge")
        return np.convolve(padded, kernel, mode="valid")


def resample_contour(
    points: Sequence[float] | np.ndarray, size: int = CONTOUR_POINTS
) -> np.ndarray:
    values = np.asarray(points, dtype=np.float64).reshape(-1)
    if values.size == 0:
        return np.zeros(size, dtype=np.float64)
    if values.size == 1:
        return np.repeat(values[0], size).astype(np.float64)
    old_axis = np.linspace(0.0, 1.0, values.size)
    new_axis = np.linspace(0.0, 1.0, size)
    return np.interp(new_axis, old_axis, values)


def _resample_evidence(values: np.ndarray, size: int = CONTOUR_POINTS) -> np.ndarray:
    finite = np.asarray(values, dtype=np.float64)
    if finite.size == 0:
        return np.ones(size, dtype=np.float64)
    return resample_contour(finite, size)


def extract_features(
    points: Sequence[float] | np.ndarray,
    *,
    duration_s: float = 0.5,
    voiced_fraction: float = 1.0,
    longest_voicing_gap_ms: float = 0.0,
    rms_contour: Sequence[float] | np.ndarray | None = None,
) -> ContourFeatures:
    contour = resample_contour(points, CONTOUR_POINTS)
    x = np.linspace(0.0, 1.0, contour.size)
    edge = max(3, contour.size // 10)
    start = float(np.median(contour[:edge]))
    end = float(np.median(contour[-edge:]))
    slope = float(np.polyfit(x, contour, 1)[0])
    midpoint = contour.size // 2
    slope_first = float(np.polyfit(x[:midpoint], contour[:midpoint], 1)[0])
    slope_second = float(np.polyfit(x[midpoint:], contour[midpoint:], 1)[0])
    curvature = slope_second - slope_first
    pitch_range = float(np.percentile(contour, 95) - np.percentile(contour, 5))
    minimum_index = int(np.argmin(contour))
    minimum = float(contour[minimum_index])
    dip_position = minimum_index / max(1, contour.size - 1)
    recovery = float(end - minimum)
    tail_start = int(contour.size * 0.68)
    final_rise = float(np.polyfit(x[tail_start:], contour[tail_start:], 1)[0])

    rms = _resample_evidence(np.asarray(rms_contour) if rms_contour is not None else np.ones(1))
    center = float(np.median(rms[int(0.42 * rms.size) : int(0.62 * rms.size)]))
    flanks = float(
        np.median(
            np.concatenate(
                (
                    rms[int(0.18 * rms.size) : int(0.38 * rms.size)],
                    rms[int(0.66 * rms.size) : int(0.86 * rms.size)],
                )
            )
        )
    )
    central_rms_dip = float(np.clip(1.0 - center / max(flanks, 1e-8), 0.0, 1.0))
    terminal = float(np.median(rms[int(0.86 * rms.size) :]))
    preceding = float(np.median(rms[int(0.55 * rms.size) : int(0.78 * rms.size)]))
    terminal_energy_drop = float(np.clip(1.0 - terminal / max(preceding, 1e-8), 0.0, 1.0))
    return ContourFeatures(
        start=start,
        end=end,
        slope=slope,
        curvature=curvature,
        pitch_range=pitch_range,
        minimum=minimum,
        dip_position=float(dip_position),
        recovery=recovery,
        final_rise=final_rise,
        duration_s=float(duration_s),
        voiced_fraction=float(voiced_fraction),
        longest_voicing_gap_ms=float(longest_voicing_gap_ms),
        central_rms_dip=central_rms_dip,
        terminal_energy_drop=terminal_energy_drop,
    )


def extract_pitch_contour(
    samples: np.ndarray,
    sample_rate: int,
    *,
    reject_long_voicing_gaps: bool = True,
) -> PitchContour:
    """Run the shared pYIN pipeline and return a normalized 64-point contour."""

    waveform = np.asarray(samples, dtype=np.float32).reshape(-1)
    if sample_rate != SAMPLE_RATE:
        waveform = _resample_audio(waveform, sample_rate, SAMPLE_RATE)
        sample_rate = SAMPLE_RATE
    segment, initial_quality = isolate_primary_speech(waveform, sample_rate)
    try:
        from .librosa_compat import librosa
    except ImportError as error:
        raise RuntimeError("Pitch extraction requires librosa") from error

    f0, voiced_flag, voiced_probability = librosa.pyin(
        segment.astype(np.float64),
        fmin=F0_MIN_HZ,
        fmax=F0_MAX_HZ,
        sr=sample_rate,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
        fill_na=np.nan,
        center=True,
    )
    f0 = np.asarray(f0, dtype=np.float64)
    voiced = _select_voiced_frames(f0, voiced_flag, voiced_probability)
    voiced_fraction = float(np.mean(voiced)) if voiced.size else 0.0
    if int(np.sum(voiced)) < 5 or voiced_fraction < 0.32:
        raise SignalQualityError(
            SignalQualityCode.INSUFFICIENT_VOICING,
            "I could not track enough of your pitch. Hold the vowel clearly.",
            details={"voiced_fraction": voiced_fraction},
        )

    longest_gap_frames, _ = _longest_internal_gap(voiced)
    longest_gap_ms = longest_gap_frames * HOP_LENGTH / sample_rate * 1_000.0
    if reject_long_voicing_gaps and longest_gap_ms > 180.0:
        raise SignalQualityError(
            SignalQualityCode.VOICING_GAP,
            "Your voice broke for too long to grade this take. Try once more.",
            details={"longest_gap_ms": longest_gap_ms},
        )

    corrected = _remove_octave_spikes(f0)
    valid_indices = np.flatnonzero(voiced & np.isfinite(corrected))
    full_axis = np.arange(corrected.size)
    interpolated = np.interp(full_axis, valid_indices, corrected[valid_indices])
    semitones = 12.0 * np.log2(interpolated / np.median(interpolated[valid_indices]))
    semitones = _smooth(semitones)
    points = resample_contour(semitones, CONTOUR_POINTS)
    rms = _frame_rms(segment)
    quality = SignalQuality(
        peak=initial_quality.peak,
        rms=initial_quality.rms,
        clipping_fraction=initial_quality.clipping_fraction,
        active_duration_s=initial_quality.active_duration_s,
        total_duration_s=initial_quality.total_duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_gap_ms,
        island_count=initial_quality.island_count,
    )
    features = extract_features(
        points,
        duration_s=initial_quality.active_duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_gap_ms,
        rms_contour=rms,
    )
    return PitchContour(
        points=points,
        features=features,
        quality=quality,
        raw_f0_hz=f0,
        raw_voiced=voiced,
    )


def extract_pitch_contour_fast(
    samples: np.ndarray,
    sample_rate: int,
    *,
    reject_long_voicing_gaps: bool = True,
) -> PitchContour:
    """Extract the same contour contract with YIN and energy-based voicing.

    This path avoids pYIN's first-request JIT cost on a newly scaled hosted
    instance. Warm instances continue to use the authoritative pYIN extractor;
    both paths share speech isolation, normalization, features, and templates.
    """

    waveform = np.asarray(samples, dtype=np.float32).reshape(-1)
    if sample_rate != SAMPLE_RATE:
        waveform = _resample_audio(waveform, sample_rate, SAMPLE_RATE)
        sample_rate = SAMPLE_RATE
    segment, initial_quality = isolate_primary_speech(waveform, sample_rate)
    try:
        from .librosa_compat import librosa
    except ImportError as error:
        raise RuntimeError("Pitch extraction requires librosa") from error

    f0 = np.asarray(
        librosa.yin(
            segment.astype(np.float64),
            fmin=F0_MIN_HZ,
            fmax=F0_MAX_HZ,
            sr=sample_rate,
            frame_length=FRAME_LENGTH,
            hop_length=HOP_LENGTH,
            center=True,
        ),
        dtype=np.float64,
    )
    rms = _frame_rms(segment)
    if rms.size != f0.size:
        rms = np.interp(
            np.linspace(0.0, 1.0, f0.size),
            np.linspace(0.0, 1.0, max(1, rms.size)),
            rms if rms.size else np.zeros(1, dtype=np.float64),
        )
    positive_rms = rms[rms > 1e-6]
    typical_rms = float(np.median(positive_rms)) if positive_rms.size else 0.0
    peak_rms = float(np.max(rms)) if rms.size else 0.0
    low_energy_floor = max(0.006, typical_rms * 0.22)
    high_energy_floor = max(low_energy_floor, peak_rms * 0.18)
    low_energy = rms >= low_energy_floor
    high_indices = np.flatnonzero(rms >= high_energy_floor)
    if high_indices.size:
        onset = int(high_indices[0])
        offset = int(high_indices[-1])
        while offset + 1 < low_energy.size and low_energy[offset + 1]:
            offset += 1
        frame_indices = np.arange(rms.size)
        energy_voiced = (
            low_energy & (frame_indices >= onset) & (frame_indices <= offset)
        )
    else:
        energy_voiced = low_energy
    voiced = np.isfinite(f0) & energy_voiced
    voiced_fraction = float(np.mean(voiced)) if voiced.size else 0.0
    if int(np.sum(voiced)) < 5 or voiced_fraction < 0.28:
        raise SignalQualityError(
            SignalQualityCode.INSUFFICIENT_VOICING,
            "I could not track enough of your pitch. Hold the vowel clearly.",
            details={"voiced_fraction": voiced_fraction, "extractor": "yin"},
        )

    longest_gap_frames, _ = _longest_internal_gap(voiced)
    longest_gap_ms = longest_gap_frames * HOP_LENGTH / sample_rate * 1_000.0
    if reject_long_voicing_gaps and longest_gap_ms > 180.0:
        raise SignalQualityError(
            SignalQualityCode.VOICING_GAP,
            "Your voice broke for too long to grade this take. Try once more.",
            details={"longest_gap_ms": longest_gap_ms, "extractor": "yin"},
        )

    tracked_f0 = f0.copy()
    tracked_f0[~voiced] = np.nan
    corrected = _remove_octave_spikes(tracked_f0)
    valid_indices = np.flatnonzero(voiced & np.isfinite(corrected))
    while valid_indices.size >= 6:
        first = int(valid_indices[0])
        neighbor = float(np.median(corrected[valid_indices[1:6]]))
        if abs(12.0 * math.log2(corrected[first] / neighbor)) <= 7.0:
            break
        voiced[first] = False
        corrected[first] = np.nan
        valid_indices = np.flatnonzero(voiced & np.isfinite(corrected))
    valid_indices = np.flatnonzero(voiced & np.isfinite(corrected))
    full_axis = np.arange(corrected.size)
    interpolated = np.interp(full_axis, valid_indices, corrected[valid_indices])
    semitones = 12.0 * np.log2(interpolated / np.median(interpolated[valid_indices]))
    points = resample_contour(_smooth(semitones), CONTOUR_POINTS)
    quality = SignalQuality(
        peak=initial_quality.peak,
        rms=initial_quality.rms,
        clipping_fraction=initial_quality.clipping_fraction,
        active_duration_s=initial_quality.active_duration_s,
        total_duration_s=initial_quality.total_duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_gap_ms,
        island_count=initial_quality.island_count,
    )
    features = extract_features(
        points,
        duration_s=initial_quality.active_duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_gap_ms,
        rms_contour=rms,
    )
    return PitchContour(
        points=points,
        features=features,
        quality=quality,
        raw_f0_hz=f0,
        raw_voiced=voiced,
    )


def analyze_audio(source: str | Path | bytes | bytearray | BinaryIO) -> PitchContour:
    samples, sample_rate = decode_audio(source)
    return extract_pitch_contour(samples, sample_rate)


def contour_from_points(
    points: Sequence[float] | np.ndarray,
    *,
    duration_s: float = 0.5,
    voiced_fraction: float = 1.0,
    longest_voicing_gap_ms: float = 0.0,
    central_rms_dip: float = 0.0,
    terminal_energy_drop: float = 0.0,
) -> PitchContour:
    """Construct an analysis object for fixtures and committed demo contours."""

    contour = resample_contour(points, CONTOUR_POINTS)
    features = extract_features(
        contour,
        duration_s=duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_voicing_gap_ms,
    )
    features = ContourFeatures(
        **{
            **features.as_dict(),
            "central_rms_dip": central_rms_dip,
            "terminal_energy_drop": terminal_energy_drop,
        }
    )
    quality = SignalQuality(
        peak=0.5,
        rms=0.1,
        clipping_fraction=0.0,
        active_duration_s=duration_s,
        total_duration_s=duration_s,
        voiced_fraction=voiced_fraction,
        longest_voicing_gap_ms=longest_voicing_gap_ms,
    )
    return PitchContour(
        points=contour,
        features=features,
        quality=quality,
        raw_f0_hz=np.zeros(0),
        raw_voiced=np.zeros(0, dtype=bool),
    )


def expected_tone_contour(tone: Tone | str, accent: Accent | str = Accent.NORTH) -> np.ndarray:
    """Return a broad acoustic prior used only to validate generated targets."""

    resolved = canonical_tone(tone)
    resolved_accent = canonical_accent(accent)
    x = np.linspace(0.0, 1.0, CONTOUR_POINTS)
    if resolved is Tone.NGANG:
        values = 0.12 * (x - 0.5)
    elif resolved is Tone.HUYEN:
        values = 1.4 - 3.0 * x + 0.35 * x**2
    elif resolved is Tone.SAC:
        values = -1.2 + 0.4 * x + 4.0 * x**2
    elif resolved is Tone.HOI:
        values = np.where(x < 0.58, 1.0 - 4.5 * x, -1.61 + 2.6 * (x - 0.58) / 0.42)
    elif resolved is Tone.NGA and resolved_accent is Accent.SOUTH:
        values = np.where(x < 0.58, 1.0 - 4.3 * x, -1.49 + 2.5 * (x - 0.58) / 0.42)
    elif resolved is Tone.NGA:
        values = -1.2 + 3.6 * x + 0.65 * np.tanh((x - 0.55) * 10.0)
    else:
        values = 1.0 - 2.1 * x - 1.4 * x**3
    return values - np.median(values)


def constrained_dtw_distance(
    left: Sequence[float] | np.ndarray,
    right: Sequence[float] | np.ndarray,
    *,
    window: int = 8,
) -> float:
    """Sakoe-Chiba constrained DTW, normalized by path length and pitch scale."""

    a = resample_contour(left, CONTOUR_POINTS)
    b = resample_contour(right, CONTOUR_POINTS)
    length = a.size
    width = max(window, abs(a.size - b.size))
    cost = np.full((length + 1, length + 1), np.inf)
    steps = np.zeros((length + 1, length + 1), dtype=np.int32)
    cost[0, 0] = 0.0
    for row in range(1, length + 1):
        for column in range(max(1, row - width), min(length, row + width) + 1):
            choices = (
                cost[row - 1, column],
                cost[row, column - 1],
                cost[row - 1, column - 1],
            )
            choice = int(np.argmin(choices))
            previous = ((row - 1, column), (row, column - 1), (row - 1, column - 1))[choice]
            cost[row, column] = choices[choice] + abs(a[row - 1] - b[column - 1])
            steps[row, column] = steps[previous] + 1
    return float(cost[length, length] / max(1, steps[length, length]) / 3.0)


_FEATURE_FIELDS = (
    "start",
    "end",
    "slope",
    "curvature",
    "pitch_range",
    "minimum",
    "dip_position",
    "recovery",
    "final_rise",
    "duration_s",
)

_DEFAULT_FEATURE_SCALES = np.array([1.5, 1.5, 3.0, 5.0, 2.5, 1.5, 0.25, 2.0, 3.0, 0.22])


def _feature_vector(features: ContourFeatures) -> np.ndarray:
    return np.asarray(
        [getattr(features, field_name) for field_name in _FEATURE_FIELDS],
        dtype=np.float64,
    )


def robust_feature_scales(templates: Sequence[ToneTemplate]) -> np.ndarray:
    if len(templates) < 3:
        return _DEFAULT_FEATURE_SCALES.copy()
    matrix = np.vstack([_feature_vector(template.features) for template in templates])
    median = np.median(matrix, axis=0)
    mad = np.median(np.abs(matrix - median), axis=0) * 1.4826
    return cast(np.ndarray, np.maximum(mad, _DEFAULT_FEATURE_SCALES * 0.35))


def feature_distance(
    left: ContourFeatures,
    right: ContourFeatures,
    scales: Sequence[float] | np.ndarray | None = None,
) -> float:
    resolved_scales = (
        _DEFAULT_FEATURE_SCALES if scales is None else np.asarray(scales, dtype=np.float64)
    )
    delta = np.abs(_feature_vector(left) - _feature_vector(right)) / resolved_scales
    delta = np.minimum(delta, 4.0)
    return float(np.mean(delta))


def _cue_distance(left: ContourFeatures, right: ContourFeatures) -> float:
    return float(
        np.mean(
            (
                abs(left.central_rms_dip - right.central_rms_dip) / 0.28,
                abs(left.longest_voicing_gap_ms - right.longest_voicing_gap_ms) / 70.0,
                abs(left.terminal_energy_drop - right.terminal_energy_drop) / 0.30,
            )
        )
    )


_CONFUSABLE_PAIRS = {
    frozenset((Tone.HOI, Tone.NGA)),
    frozenset((Tone.SAC, Tone.NGA)),
    frozenset((Tone.HUYEN, Tone.NANG)),
}


def _softmax_probabilities(scores: Mapping[Any, float], temperature: float) -> dict[Any, float]:
    labels = list(scores)
    values = -np.asarray([scores[label] for label in labels], dtype=np.float64) / max(
        temperature, 1e-6
    )
    values -= np.max(values)
    exp = np.exp(values)
    probabilities = exp / max(float(np.sum(exp)), 1e-12)
    return dict(zip(labels, (float(value) for value in probabilities), strict=True))


def _representative_tone(
    family: ToneFamily,
    tone_scores: Mapping[Tone, float],
    accent: Accent,
) -> Tone:
    members = [
        tone for tone in TONE_ORDER if tone_family(tone, accent) is family and tone in tone_scores
    ]
    return min(members, key=lambda tone: tone_scores[tone])


def classify_contour(
    analysis: PitchContour,
    templates: Sequence[ToneTemplate],
    *,
    accent: Accent | str = Accent.NORTH,
    scoring_mode: ScoringMode | str = ScoringMode.SIX_TONE,
    temperature: float = 0.32,
    abstention_threshold: float = 0.43,
) -> ClassificationResult:
    """Classify without looking at the learner's intended word or tone."""

    resolved_accent = canonical_accent(accent)
    resolved_mode = ScoringMode(scoring_mode)
    available = [template for template in templates if template.accent is resolved_accent]
    if not available:
        raise ValueError(f"No templates are available for accent {resolved_accent.value!r}")
    scales = robust_feature_scales(available)
    template_scores: list[tuple[ToneTemplate, float, float]] = []
    for template in available:
        dtw = constrained_dtw_distance(analysis.points, template.contour)
        features = feature_distance(analysis.features, template.features, scales)
        template_scores.append(
            (
                template,
                0.65 * dtw + 0.35 * features,
                _cue_distance(analysis.features, template.features),
            )
        )

    tone_scores: dict[Tone, float] = {}
    cue_scores: dict[Tone, float] = {}
    for tone in TONE_ORDER:
        entries = sorted(
            (score, cue) for template, score, cue in template_scores if template.tone is tone
        )
        if not entries:
            continue
        count = min(2, len(entries))
        tone_scores[tone] = float(np.mean([score for score, _ in entries[:count]]))
        cue_scores[tone] = float(np.mean([cue for _, cue in entries[:count]]))

    ranked = sorted(tone_scores, key=tone_scores.get)  # type: ignore[arg-type]
    if len(ranked) >= 2 and frozenset(ranked[:2]) in _CONFUSABLE_PAIRS:
        base_margin = tone_scores[ranked[1]] - tone_scores[ranked[0]]
        if base_margin <= 0.20:
            for tone in ranked[:2]:
                tone_scores[tone] += 0.20 * cue_scores[tone]

    tone_probabilities = _softmax_probabilities(tone_scores, temperature)
    ranked = sorted(tone_scores, key=tone_scores.get)  # type: ignore[arg-type]
    if resolved_mode is ScoringMode.SIX_TONE:
        detected_tone = ranked[0]
        detected_family = tone_family(detected_tone, resolved_accent)
        confidence = min(0.95, tone_probabilities[detected_tone])
        result_scores = {tone.value: score for tone, score in tone_scores.items()}
        exact_verified = True
    else:
        family_scores: dict[ToneFamily, float] = {}
        for family in FAMILY_ORDER:
            members = sorted(
                tone_scores[tone]
                for tone in tone_scores
                if tone_family(tone, resolved_accent) is family
            )
            if members:
                family_scores[family] = float(np.mean(members[: min(2, len(members))]))
        family_probabilities = _softmax_probabilities(family_scores, temperature)
        detected_family = min(family_scores, key=family_scores.get)  # type: ignore[arg-type]
        detected_tone = _representative_tone(detected_family, tone_scores, resolved_accent)
        confidence = min(0.95, family_probabilities[detected_family])
        result_scores = {family.value: score for family, score in family_scores.items()}
        exact_verified = False

    alternatives = tuple(
        ToneAlternative(
            tone=tone,
            family=tone_family(tone, resolved_accent),
            score=float(tone_scores[tone]),
            probability=float(tone_probabilities[tone]),
        )
        for tone in sorted(tone_scores, key=tone_scores.get)[:3]  # type: ignore[arg-type]
    )
    return ClassificationResult(
        tone=detected_tone,
        family=detected_family,
        confidence=float(confidence),
        scoring_mode=resolved_mode,
        exact_verified=exact_verified,
        needs_retry=confidence < abstention_threshold,
        alternatives=alternatives,
        scores=result_scores,
    )


def classify_audio(
    source: str | Path | bytes | bytearray | BinaryIO,
    templates: Sequence[ToneTemplate],
    *,
    accent: Accent | str = Accent.NORTH,
    scoring_mode: ScoringMode | str = ScoringMode.SIX_TONE,
    temperature: float = 0.32,
    abstention_threshold: float = 0.43,
) -> tuple[PitchContour, ClassificationResult]:
    analysis = analyze_audio(source)
    result = classify_contour(
        analysis,
        templates,
        accent=accent,
        scoring_mode=scoring_mode,
        temperature=temperature,
        abstention_threshold=abstention_threshold,
    )
    return analysis, result


def feature_differences(learner: ContourFeatures, target: ContourFeatures) -> dict[str, float]:
    """Machine-readable differences consumed by either coach implementation."""

    return {
        field_name: round(float(getattr(learner, field_name) - getattr(target, field_name)), 5)
        for field_name in _FEATURE_FIELDS
    } | {
        "central_rms_dip": round(learner.central_rms_dip - target.central_rms_dip, 5),
        "terminal_energy_drop": round(
            learner.terminal_energy_drop - target.terminal_energy_drop, 5
        ),
    }


def tips_from_differences(differences: Mapping[str, float]) -> list[str]:
    """Convert numeric feature differences into stable physical coaching cues."""

    tips: list[str] = []
    if differences.get("start", 0.0) > 1.0:
        tips.append("started_too_high")
    elif differences.get("start", 0.0) < -1.0:
        tips.append("started_too_low")
    if differences.get("end", 0.0) > 1.1:
        tips.append("ended_too_high")
    elif differences.get("end", 0.0) < -1.1:
        tips.append("ended_too_low")
    if differences.get("final_rise", 0.0) < -1.4:
        tips.append("no_final_rise")
    if differences.get("dip_position", 0.0) < -0.14:
        tips.append("dip_too_early")
    elif differences.get("dip_position", 0.0) > 0.14:
        tips.append("dip_too_late")
    if differences.get("pitch_range", 0.0) < -1.0:
        tips.append("range_too_flat")
    if differences.get("duration_s", 0.0) < -0.16:
        tips.append("too_short")
    return tips or ["match_the_target_shape"]


def _candidate_rule_failures(
    features: ContourFeatures,
    tone: Tone,
    accent: Accent,
) -> list[str]:
    reasons: list[str] = []
    if tone is Tone.NGANG and (abs(features.slope) > 1.6 or features.pitch_range > 2.4):
        reasons.append("not_level")
    elif tone is Tone.HUYEN and (features.end >= features.start - 0.7 or features.slope >= -0.7):
        reasons.append("no_fall")
    elif tone is Tone.SAC and (features.end <= features.start + 1.0 or features.final_rise <= 0.7):
        reasons.append("no_rise")
    elif tone is Tone.HOI and (
        features.dip_position < 0.25 or features.dip_position > 0.82 or features.recovery < 0.45
    ):
        reasons.append("no_dip_recovery")
    elif tone is Tone.NGA:
        if accent is Accent.NORTH and features.end <= features.start + 0.8:
            reasons.append("no_broken_rise")
        if accent is Accent.SOUTH and features.recovery < 0.35:
            reasons.append("no_merged_dip")
    elif tone is Tone.NANG and (
        features.end >= features.start - 0.5
        or (features.duration_s > 0.75 and features.terminal_energy_drop < 0.12)
    ):
        reasons.append("not_short_low")
    return reasons


def _range_adapted_validation_scores(analysis: PitchContour, accent: Accent) -> dict[Tone, float]:
    """Compare target shape after adapting broad priors to its pitch excursion.

    The provider's `cedar` voice often realizes emphatic rising tones over a
    much wider semitone range than the hand-authored prior. This retry changes
    the prior's amplitude, not its direction or timing; the independent tone
    rules and separation gate still referee the result.
    """

    scores: dict[Tone, float] = {}
    for candidate in TONE_ORDER:
        prior = expected_tone_contour(candidate, accent)
        prior_features = extract_features(prior)
        if candidate is not Tone.NGANG:
            scale = float(
                np.clip(
                    analysis.features.pitch_range / max(prior_features.pitch_range, 1e-6),
                    0.6,
                    3.0,
                )
            )
            prior = prior * scale
            prior_features = extract_features(prior)
        scores[candidate] = constrained_dtw_distance(analysis.points, prior) + 0.25 * (
            feature_distance(analysis.features, prior_features)
        )
    return scores


def _southern_dipping_family_evidence(features: ContourFeatures, tone: Tone) -> bool:
    """Verify the merged Southern hỏi/ngã family with pitch and creak evidence."""

    if tone not in {Tone.HOI, Tone.NGA}:
        return False
    pitch_descent = features.start - features.minimum
    has_dip_shape = (
        0.25 <= features.dip_position <= 0.70 and pitch_descent >= 0.60 and features.recovery >= 1.0
    )
    has_creak_evidence = features.central_rms_dip >= 0.20 or features.longest_voicing_gap_ms >= 40.0
    return has_dip_shape and has_creak_evidence


def validate_target_candidate(
    source: str | Path | bytes | bytearray | BinaryIO | PitchContour,
    expected_tone: Tone | str,
    *,
    accent: Accent | str = Accent.NORTH,
    lexical_verified: bool = True,
) -> CandidateValidation:
    """Referee one generated target before it can enter the manifest."""

    tone = canonical_tone(expected_tone)
    resolved_accent = canonical_accent(accent)
    try:
        analysis = source if isinstance(source, PitchContour) else analyze_audio(source)
    except SignalQualityError as error:
        return CandidateValidation(
            passed=False,
            tone=tone,
            accent=resolved_accent,
            shape_score=math.inf,
            separation_margin=-math.inf,
            reason_codes=(error.code.value,),
        )
    expected_scores = {
        candidate: constrained_dtw_distance(
            analysis.points, expected_tone_contour(candidate, resolved_accent)
        )
        + 0.25
        * feature_distance(
            analysis.features,
            extract_features(expected_tone_contour(candidate, resolved_accent)),
        )
        for candidate in TONE_ORDER
    }
    expected_score = expected_scores[tone]
    competing_score = min(
        score for candidate, score in expected_scores.items() if candidate is not tone
    )
    margin = competing_score - expected_score
    reasons = [] if lexical_verified else ["lexical_mismatch"]
    rule_failures = _candidate_rule_failures(analysis.features, tone, resolved_accent)
    reasons.extend(rule_failures)
    if not rule_failures and (expected_score > 1.15 or margin < -0.08):
        adapted_scores = _range_adapted_validation_scores(analysis, resolved_accent)
        adapted_expected = adapted_scores[tone]
        adapted_competing = min(
            score for candidate, score in adapted_scores.items() if candidate is not tone
        )
        adapted_margin = adapted_competing - adapted_expected
        if adapted_expected <= 1.15 and adapted_margin >= -0.08:
            expected_score = adapted_expected
            margin = adapted_margin
    accent_family_verified = (
        resolved_accent is Accent.SOUTH
        and not rule_failures
        and _southern_dipping_family_evidence(analysis.features, tone)
    )
    if expected_score > 1.15 and not accent_family_verified:
        reasons.append("shape_distance")
    if margin < -0.08 and not accent_family_verified:
        reasons.append("wrong_tone_shape")
    return CandidateValidation(
        passed=not reasons,
        tone=tone,
        accent=resolved_accent,
        shape_score=float(expected_score),
        separation_margin=float(margin),
        reason_codes=tuple(dict.fromkeys(reasons)),
        contour=analysis,
        accent_family_verified=accent_family_verified,
    )


def select_best_candidate(
    candidates: Iterable[CandidateValidation],
) -> CandidateValidation | None:
    passing = [candidate for candidate in candidates if candidate.passed]
    if not passing:
        return None
    return max(
        passing,
        key=lambda candidate: (candidate.separation_margin, -candidate.shape_score),
    )
