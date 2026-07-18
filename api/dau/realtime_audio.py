"""Bounded one-utterance speech generation through the Realtime family."""

from __future__ import annotations

import base64
import json
import wave
from collections.abc import Iterable
from io import BytesIO

from websockets.sync.client import connect

from .models import (
    NORTHERN_VOICE_PROMPT,
    REFERENCE_MODEL,
    SOUTHERN_VOICE_PROMPT,
    SPEECH_MODEL,
)
from .settings import openai_api_key

REALTIME_URL = "wss://api.openai.com/v1/realtime"
SAMPLE_RATE = 24_000


def voice_prompt(accent: str) -> str:
    if accent not in {"north", "south"}:
        raise ValueError(f"Unsupported accent: {accent}")
    return SOUTHERN_VOICE_PROMPT if accent == "south" else NORTHERN_VOICE_PROMPT


def _pcm_to_wav(chunks: Iterable[bytes]) -> bytes:
    stream = BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for chunk in chunks:
            output.writeframes(chunk)
    return stream.getvalue()


def _usable_incomplete_audio(
    response: dict[str, object], *, allow_incomplete_audio: bool, has_audio: bool
) -> bool:
    """Allow only token-capped partial audio into a downstream validation gate."""

    details = response.get("status_details")
    reason = details.get("reason") if isinstance(details, dict) else None
    return (
        allow_incomplete_audio
        and has_audio
        and response.get("status") == "incomplete"
        and reason == "max_output_tokens"
    )


def synthesize_utterance(
    text: str,
    *,
    accent: str,
    model: str = SPEECH_MODEL,
    instructions: str | None = None,
    max_output_tokens: int = 192,
    timeout_seconds: float = 45.0,
    allow_incomplete_audio: bool = False,
) -> bytes:
    """Open one Realtime session, collect one Cô Linh utterance, then close it."""

    if model not in {SPEECH_MODEL, REFERENCE_MODEL}:
        raise ValueError("Dấu never silently falls back to an unapproved speech model")
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for live speech generation")
    system = instructions or voice_prompt(accent)
    request_text = (
        f"Speak only this Vietnamese text exactly once, with no introduction or commentary: {text}"
    )
    audio_chunks: list[bytes] = []
    with connect(
        f"{REALTIME_URL}?model={model}",
        additional_headers={"Authorization": f"Bearer {key}"},
        open_timeout=timeout_seconds,
        close_timeout=5,
    ) as websocket:
        websocket.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": model,
                        "output_modalities": ["audio"],
                        "reasoning": {"effort": "low"},
                        "audio": {
                            "output": {
                                "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                                "voice": "cedar",
                            }
                        },
                        "instructions": system,
                    },
                },
                ensure_ascii=False,
            )
        )
        websocket.send(
            json.dumps(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": request_text}],
                    },
                },
                ensure_ascii=False,
            )
        )
        websocket.send(
            json.dumps(
                {
                    "type": "response.create",
                    "response": {
                        "output_modalities": ["audio"],
                        "max_output_tokens": max_output_tokens,
                    },
                }
            )
        )
        while True:
            raw = websocket.recv(timeout=timeout_seconds)
            event = json.loads(raw)
            event_type = event.get("type")
            if event_type in {"response.output_audio.delta", "response.audio.delta"}:
                audio_chunks.append(base64.b64decode(event["delta"]))
            elif event_type == "error":
                message = event.get("error", {}).get("message", "Realtime speech failed")
                raise RuntimeError(message)
            elif event_type == "response.done":
                response = event.get("response", {})
                status = response.get("status")
                if status not in {None, "completed"} and not _usable_incomplete_audio(
                    response,
                    allow_incomplete_audio=allow_incomplete_audio,
                    has_audio=bool(audio_chunks),
                ):
                    details = response.get("status_details")
                    raise RuntimeError(f"Realtime response ended with status {status}: {details}")
                break
    if not audio_chunks:
        raise RuntimeError("Realtime returned no audio")
    return _pcm_to_wav(audio_chunks)
