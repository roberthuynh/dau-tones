"""FastAPI application for local development and the Vercel Python service."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Annotated, Any, cast

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .coach import coach, generate_drill
from .content import demo_document, echo_document, public_words, reference_corpus_is_complete
from .echo import (
    align_transcript,
    detected_tone_metadata,
    literal_explanation,
    meaning_status,
    normalize_text,
    practice_word_ids,
)
from .models import IMAGE_MODEL, TEXT_MODEL, TRANSCRIPTION_MODEL
from .schemas import (
    AnalysisResponse,
    CoachRequest,
    DrillRequest,
    EchoScenesResponse,
    EchoSpeakRequest,
    EchoTranscribeResponse,
)
from .settings import (
    AI_TIMEOUT_SECONDS,
    MAX_UPLOAD_BYTES,
    REPO_ROOT,
    has_openai_key,
    openai_api_key,
)

app = FastAPI(
    title="Dấu API",
    summary="Deterministic DSP grading and optional OpenAI coaching for Vietnamese tones.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

router = APIRouter()
REVEAL_CACHE: dict[str, dict[str, Any]] = {}
REVEAL_LOCK = Lock()
REVEAL_GENERATION_LOCKS: dict[str, Lock] = {}


class EchoExplanation(BaseModel):
    explanation: str = Field(min_length=4, max_length=220)


class EchoRevealRequest(BaseModel):
    explanation: str = Field(min_length=4, max_length=220)


def _openai_client(key: str, *, timeout: float) -> Any:
    """Keep the optional OpenAI SDK off the local DSP import path."""

    from openai import OpenAI

    return OpenAI(api_key=key, timeout=timeout, max_retries=0)


def warm_analysis_runtime(timing: dict[str, float]) -> bool:
    """Load the pitch stack only when the compatibility warmup is explicitly called."""

    from .analysis_service import warm_analysis_runtime as warm

    return warm(timing)


def _health() -> dict[str, Any]:
    key = has_openai_key()
    modes = public_words().get("scoring_modes", {"north": "four_family", "south": "four_family"})
    return {
        "status": "ok",
        "ready": True,
        "reference_corpus_validated": reference_corpus_is_complete(),
        "scoring_modes": modes,
        "capabilities": {
            "local_dsp": True,
            "ai_coaching": key,
            "generated_drills": key,
            "live_echo_transcription": key,
            "live_echo_art": key,
            "cached_echo_speech": True,
        },
        "banner": None if key else "Add an OpenAI key for AI coaching",
    }


def _server_timing(timing: dict[str, float]) -> str:
    return ", ".join(
        f"{name};dur={duration:.2f}" for name, duration in timing.items() if duration >= 0.0
    )


@router.get("/healthz")
def healthz() -> dict[str, Any]:
    return _health()


@router.post("/analysis/warmup")
def analysis_warmup() -> JSONResponse:
    timing: dict[str, float] = {}
    cold_started = warm_analysis_runtime(timing)
    return JSONResponse(
        {"status": "ready", "cold_started": cold_started},
        headers={"Server-Timing": _server_timing(timing)},
    )


@router.get("/words")
def words() -> dict[str, Any]:
    return public_words()


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    audio: Annotated[UploadFile, File()],
    word: Annotated[str, Form()],
    intended_tone: Annotated[str, Form()],
    accent: Annotated[str, Form()] = "north",
) -> JSONResponse:
    from . import analysis_service

    payload = await audio.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, detail={"code": "audio_too_large", "message": "Keep the recording under 10 MB."}
        )
    timing: dict[str, float] = {}
    try:
        result = await run_in_threadpool(
            analysis_service.analyze_recording,
            payload,
            word_id=word,
            intended_tone=intended_tone,
            accent=accent,
            timing=timing,
        )
        return JSONResponse(
            AnalysisResponse.model_validate(result).model_dump(mode="json"),
            headers={"Server-Timing": _server_timing(timing)},
        )
    except analysis_service.SignalQualityError as error:
        return JSONResponse(
            status_code=422,
            content={"detail": {**error.as_dict(), "needs_retry": True}},
            headers={"Server-Timing": _server_timing(timing)},
        )
    except ValueError as error:
        raise HTTPException(
            400, detail={"code": "invalid_request", "message": str(error)}
        ) from error


@router.post("/coach")
def coaching(request: CoachRequest) -> dict[str, Any]:
    return coach(request).model_dump()


@router.post("/drills/generate")
def drills(request: DrillRequest) -> dict[str, Any]:
    return generate_drill(request)


def _resolve_repo_file(relative_path: str) -> Path:
    candidate = (REPO_ROOT / relative_path).resolve()
    if REPO_ROOT not in candidate.parents or not candidate.is_file():
        raise HTTPException(
            404,
            detail={"code": "asset_missing", "message": "That committed sample is unavailable."},
        )
    return candidate


@router.get("/targets/{accent}/{word_id}.wav")
def target_audio(accent: str, word_id: str) -> FileResponse:
    if accent not in {"north", "south"}:
        raise HTTPException(404, detail="Unknown accent")
    return FileResponse(
        _resolve_repo_file(f"targets/{accent}/{word_id}.wav"),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/demos/{demo_id}.wav")
def demo_audio(demo_id: str) -> FileResponse:
    entries = demo_document().get("analyzer_demos", []) + demo_document().get("echo_demos", [])
    item = next((entry for entry in entries if entry.get("id") == demo_id), None)
    if item is None:
        raise HTTPException(404, detail="Unknown demo")
    return FileResponse(
        _resolve_repo_file(item["recording_path"]),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.get("/demos")
def demos() -> dict[str, Any]:
    document = demo_document()
    return {
        "analyzer_demos": [
            {**item, "audio_url": f"/api/demos/{item['id']}.wav"}
            for item in document.get("analyzer_demos", [])
        ],
        "echo_demos": [
            {**item, "audio_url": f"/api/demos/{item['id']}.wav"}
            for item in document.get("echo_demos", [])
        ],
    }


@router.get("/echo/sentences")
def echo_sentences() -> dict[str, Any]:
    """Compatibility alias: expose learner turns in the legacy sentence shape."""

    sentences = []
    for item in echo_document().get("sentences", []):
        sentences.append(
            {
                **item,
                "audio_urls": {
                    accent: f"/api/echo/speak/{accent}/{item['id']}.wav"
                    for accent in ("north", "south")
                },
            }
        )
    return {"sentences": sentences}


def _public_echo_turn(turn: dict[str, Any]) -> dict[str, Any]:
    return {
        **turn,
        "audio_urls": {
            accent: f"/audio/echo/{accent}/{turn['id']}.wav" for accent in ("north", "south")
        },
        "compatibility_audio_urls": {
            accent: f"/api/echo/speak/{accent}/{turn['id']}.wav" for accent in ("north", "south")
        },
    }


@router.get("/echo/scenes", response_model=EchoScenesResponse)
def echo_scenes() -> dict[str, Any]:
    document = echo_document()
    scenes = [
        {
            **scene,
            "offline_demo": {
                **scene["offline_demo"],
                "audio_url": f"/audio/demos/echo/{scene['offline_demo']['id']}.wav",
            },
            "turns": [_public_echo_turn(turn) for turn in scene.get("turns", [])],
        }
        for scene in document.get("scenes", [])
    ]
    return {
        "schema_version": document.get("schema_version", 2),
        "locale": document.get("locale", "vi-VN"),
        "scenes": scenes,
    }


def _echo_entry(entry_id: str) -> dict[str, Any]:
    document = echo_document()
    item = next(
        (
            entry
            for entry in document.get("turns", []) + document.get("legacy_sentences", [])
            if entry.get("id") == entry_id
        ),
        None,
    )
    if item is None:
        raise HTTPException(
            404,
            detail={"code": "unknown_sentence", "message": "Choose a seeded Echo dialogue line."},
        )
    return cast(dict[str, Any], item)


def _sentence(sentence_id: str) -> dict[str, Any]:
    """Retain the old resolver name for cached clients and tests."""

    return _echo_entry(sentence_id)


def _offline_demo(demo_id: str) -> dict[str, Any] | None:
    for scene in echo_document().get("scenes", []):
        demo = scene.get("offline_demo", {})
        if demo.get("id") == demo_id:
            return {**demo, "scene_id": scene["id"]}
    return None


def _ai_explanation(target: str, transcript: str, diff: list[dict[str, Any]], fallback: str) -> str:
    key = openai_api_key()
    if not key or all(item.get("kind") == "match" for item in diff):
        return fallback
    try:
        client = _openai_client(key, timeout=AI_TIMEOUT_SECONDS)
        response = client.responses.parse(
            model=TEXT_MODEL,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            input=[
                {
                    "role": "system",
                    "content": (
                        "Explain the literal meaning created by this Vietnamese transcript "
                        "difference in one accurate, playful sentence. Use only supplied curated "
                        "meanings; do not invent one."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"target": target, "heard": transcript, "diff": diff, "fallback": fallback},
                        ensure_ascii=False,
                    ),
                },
            ],
            text_format=EchoExplanation,
            # Leave room for GPT-5.6's low-effort reasoning plus the tiny JSON
            # payload. Smaller caps can finish with output_parsed=None.
            max_output_tokens=400,
        )
        return response.output_parsed.explanation if response.output_parsed else fallback
    except Exception:
        return fallback


def _reveal_cache_id(explanation: str) -> str:
    return hashlib.sha256(f"echo-reveal-v1:{normalize_text(explanation)}".encode()).hexdigest()[:16]


def _generate_reveal(explanation: str) -> bytes:
    key = openai_api_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for live Echo art")
    client = _openai_client(key, timeout=120)
    result = client.images.generate(
        model=IMAGE_MODEL,
        prompt=(
            "Flat 2D minimal illustration, warm palette on near-black, single "
            "centered subject, no text, no border. Illustrate this playful literal "
            "Vietnamese misunderstanding: " + explanation
        ),
        size="1024x1024",
        quality="medium",
        output_format="png",
        n=1,
    )
    encoded = result.data[0].b64_json
    if not encoded:
        raise RuntimeError("The image model returned no PNG data")
    return base64.b64decode(encoded)


@router.post("/echo/transcribe", response_model=EchoTranscribeResponse)
async def echo_transcribe(
    turn_id: Annotated[str | None, Form()] = None,
    sentence_id: Annotated[str | None, Form()] = None,
    demo_id: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    requested_id = turn_id or sentence_id
    if not requested_id:
        raise HTTPException(
            400,
            detail={"code": "missing_turn", "message": "Choose a dialogue line to practice."},
        )
    sentence = _echo_entry(requested_id)
    resolved_turn_id = sentence["id"]
    source = "fixture"
    transcript: str
    if demo_id:
        demo = next(
            (
                entry
                for entry in demo_document().get("echo_demos", [])
                if entry.get("id") == demo_id
            ),
            None,
        )
        if demo is None:
            demo = _offline_demo(demo_id)
        demo_turn_id = (demo or {}).get("turn_id") or (demo or {}).get("sentence_id")
        if demo is None or demo_turn_id != resolved_turn_id:
            raise HTTPException(
                404, detail={"code": "unknown_demo", "message": "That Echo demo is unavailable."}
            )
        transcript = demo["committed_transcript"]
    else:
        key = openai_api_key()
        if not key:
            raise HTTPException(
                503,
                detail={
                    "code": "echo_live_requires_key",
                    "message": (
                        "Live transcript feedback needs an OpenAI key. Your recording still "
                        "stays available for replay and shadowing."
                    ),
                },
            )
        if audio is None:
            raise HTTPException(
                400, detail={"code": "missing_audio", "message": "Record the sentence first."}
            )
        payload = await audio.read(MAX_UPLOAD_BYTES + 1)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                detail={"code": "audio_too_large", "message": "Keep the recording under 10 MB."},
            )
        client = _openai_client(key, timeout=30)
        result = client.audio.transcriptions.create(
            model=TRANSCRIPTION_MODEL,
            file=(audio.filename or "echo.webm", payload, audio.content_type or "audio/webm"),
            language="vi",
            prompt=(
                "Transcribe exactly what was heard in Vietnamese NFC. Preserve the speaker's "
                "tone marks. "
                "Do not silently correct a wrong tone to this target: " + sentence["text"]
            ),
            response_format="text",
        )
        transcript = result if isinstance(result, str) else result.text
        source = TRANSCRIPTION_MODEL
    diff = align_transcript(sentence["text"], transcript)
    fallback = literal_explanation(diff)
    explanation = _ai_explanation(sentence["text"], transcript, diff, fallback)
    reveal_id = None
    if has_openai_key() and any(item.get("kind") != "match" for item in diff):
        reveal_id = _reveal_cache_id(fallback)
    practice_ids = practice_word_ids(diff)
    tone_changes = detected_tone_metadata(diff)
    return EchoTranscribeResponse.model_validate(
        {
            "sentence_id": resolved_turn_id,
            "scene_id": sentence.get("scene_id"),
            "turn_id": resolved_turn_id,
            "next_turn_id": sentence.get("next_turn_id"),
            "target_text": sentence["text"],
            "transcript": normalize_text(transcript),
            "tokens": diff,
            "practice_word_ids": practice_ids,
            "detected_tones": tone_changes,
            "meaning_status": meaning_status(diff),
            "explanation": explanation,
            "literal_explanation": fallback,
            "source": source,
            "reveal_id": reveal_id,
            "target": sentence["text"],
            "diff": diff,
        }
    ).model_dump(mode="json")


@router.post("/echo/reveals/{reveal_id}")
def generate_echo_reveal(reveal_id: str, request: EchoRevealRequest) -> Response:
    """Return one reveal directly so serverless instance changes cannot strand polling."""

    if reveal_id != _reveal_cache_id(request.explanation):
        raise HTTPException(
            400,
            detail={
                "code": "invalid_reveal",
                "message": "That reveal no longer matches the transcript feedback.",
            },
        )
    if not has_openai_key():
        raise HTTPException(
            503,
            detail={
                "code": "reveal_requires_key",
                "message": "The text feedback is ready, but live meaning art needs an OpenAI key.",
            },
        )

    with REVEAL_LOCK:
        cached = REVEAL_CACHE.get(reveal_id)
        generation_lock = REVEAL_GENERATION_LOCKS.setdefault(reveal_id, Lock())
    if cached and cached.get("status") == "ready":
        data = cached["image"]
    else:
        with generation_lock:
            with REVEAL_LOCK:
                cached = REVEAL_CACHE.get(reveal_id)
            if cached and cached.get("status") == "ready":
                data = cached["image"]
            else:
                with REVEAL_LOCK:
                    REVEAL_CACHE[reveal_id] = {"status": "pending"}
                try:
                    data = _generate_reveal(request.explanation)
                except Exception as error:
                    with REVEAL_LOCK:
                        REVEAL_CACHE[reveal_id] = {"status": "failed"}
                    raise HTTPException(
                        502,
                        detail={
                            "code": "reveal_failed",
                            "message": (
                                "The literal meaning picture is unavailable. "
                                "The transcript feedback still works."
                            ),
                        },
                    ) from error
                with REVEAL_LOCK:
                    REVEAL_CACHE[reveal_id] = {"status": "ready", "image": data}

    return Response(
        data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{reveal_id}"',
        },
    )


@router.get("/echo/reveals/{reveal_id}")
def echo_reveal(reveal_id: str) -> dict[str, Any]:
    with REVEAL_LOCK:
        item = REVEAL_CACHE.get(reveal_id, {"status": "missing"})
    return {
        "status": item["status"],
        "image_url": f"/api/echo/reveals/{reveal_id}/image" if item["status"] == "ready" else None,
    }


@router.get("/echo/reveals/{reveal_id}/image")
def echo_reveal_image(reveal_id: str) -> Response:
    with REVEAL_LOCK:
        item = REVEAL_CACHE.get(reveal_id)
    if not item or item.get("status") != "ready":
        raise HTTPException(404, detail="Reveal image not ready")
    return Response(
        item["image"], media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )


@router.get("/echo/speak/{accent}/{sentence_id}.wav")
def seeded_echo_speech(accent: str, sentence_id: str) -> FileResponse:
    _echo_entry(sentence_id)
    if accent not in {"north", "south"}:
        raise HTTPException(404, detail="Unknown accent")
    return FileResponse(
        _resolve_repo_file(f"targets/echo/{accent}/{sentence_id}.wav"),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/echo/speak")
def echo_speak(request: EchoSpeakRequest) -> Response:
    requested_id = request.turn_id or request.sentence_id
    if requested_id:
        item = _echo_entry(requested_id)
        path = REPO_ROOT / item["shadow_audio"][request.accent]
        if path.is_file():
            return FileResponse(
                path,
                media_type="audio/wav",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
        text = item["text"]
    elif request.text:
        text = request.text
    else:
        raise HTTPException(
            400, detail={"code": "missing_text", "message": "Choose a sentence to shadow."}
        )
    if not has_openai_key():
        raise HTTPException(
            503,
            detail={
                "code": "speech_unavailable",
                "message": "This uncached sentence needs an OpenAI key.",
            },
        )
    try:
        from .realtime_audio import synthesize_utterance

        wav = synthesize_utterance(text, accent=request.accent)
    except Exception as error:
        raise HTTPException(
            502,
            detail={
                "code": "speech_failed",
                "message": (
                    "Correct speech is temporarily unavailable. Try the committed sentence set."
                ),
            },
        ) from error
    return Response(
        wav, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"}
    )


app.include_router(router)
# Local Vite strips /api while Vercel may preserve a service route prefix. Both
# paths are served from the same handlers, without duplicating OpenAPI entries.
app.include_router(router, prefix="/api", include_in_schema=False)


@app.exception_handler(Exception)
async def unhandled_error(_request: Any, error: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "server_error",
                "message": (
                    "Dấu hit an unexpected error. Your recording was not stored; try once more."
                ),
            }
        },
    )
