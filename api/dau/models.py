"""Single source of truth for every active OpenAI model used by Dấu."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenAIModelConfig:
    """Pinned model roles. Older-generation substitutions are intentionally absent."""

    text: str = "gpt-5.6-sol"
    image: str = "gpt-image-2"
    transcription: str = "gpt-4o-transcribe"
    echo_speech: str = "gpt-realtime-2.1-mini"
    reference_speech: str = "gpt-realtime-2.1"


MODELS = OpenAIModelConfig()
TEXT_MODEL = MODELS.text
IMAGE_MODEL = MODELS.image
TRANSCRIPTION_MODEL = MODELS.transcription
SPEECH_MODEL = MODELS.echo_speech
REFERENCE_MODEL = MODELS.reference_speech
ACTIVE_MODEL_IDS = frozenset(
    {
        MODELS.text,
        MODELS.image,
        MODELS.transcription,
        MODELS.echo_speech,
        MODELS.reference_speech,
    }
)
ACTIVE_MODELS = {
    "text": MODELS.text,
    "image": MODELS.image,
    "transcription": MODELS.transcription,
    "speech": MODELS.echo_speech,
    "reference": MODELS.reference_speech,
}

COACH_REASONING_EFFORT = "low"
COACH_TIMEOUT_SECONDS = 12.0
REFERENCE_VOICE = "cedar"

NORTHERN_VOICE_PROMPT = (
    "Always speak natural Vietnamese with a neutral Northern Vietnamese (Hà Nội) accent. "
    "Use clear, casual everyday vocabulary. Speak warmly at a moderate pace. Avoid sounding "
    "like a foreigner reading Vietnamese. Pronounce Vietnamese names, tones, numbers, and "
    "place names carefully."
)

SOUTHERN_VOICE_PROMPT = (
    "Always speak natural Vietnamese with a modern Southern Vietnamese (Sài Gòn) accent. "
    "Use clear, casual everyday vocabulary. Speak warmly at a moderate pace. Avoid sounding "
    "like a foreigner reading Vietnamese. Pronounce Vietnamese names, tones, numbers, and "
    "place names carefully."
)
