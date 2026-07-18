"""FastAPI application for local development and the Vercel Python service."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from openai import OpenAI
from pydantic import BaseModel, Field

from .analysis_service import SignalQualityError, analyze_recording, scoring_mode
from .coach import coach, generate_drill
from .content import demo_document, echo_document, public_words
from .echo import align_transcript, literal_explanation, normalize_text
from .models import IMAGE_MODEL, TEXT_MODEL, TRANSCRIPTION_MODEL
from .realtime_audio import synthesize_utterance
from .schemas import CoachRequest, DrillRequest, EchoSpeakRequest
from .settings import (
    AI_TIMEOUT_SECONDS,
    MAX_UPLOAD_BYTES,
    REPO_ROOT,
    TARGETS_ROOT,
    has_openai_key,
    openai_api_key,
)

app = FastAPI(
    title="Dấu API",
    summary="Local DSP grading and optional OpenAI coaching for Vietnamese tones.",
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


class EchoExplanation(BaseModel):
    explanation: str = Field(min_length=4, max_length=220)


def _health() -> dict[str, Any]:
    manifest_exists = (TARGETS_ROOT / "manifest.json").exists()
    key = has_openai_key()
    return {
        "status": "ok",
        "ready": True,
        "reference_corpus_validated": manifest_exists,
        "scoring_modes": {
            "north": "six_tone" if scoring_mode("north").value == "six-tone" else "four_family",
            "south": "four_family",
        },
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


@router.get("/healthz")
def healthz() -> dict[str, Any]:
    return _health()


@router.get("/words")
def words() -> dict[str, Any]:
    return public_words()


@router.post("/analyze")
async def analyze(
    audio: Annotated[UploadFile, File()],
    word: Annotated[str, Form()],
    intended_tone: Annotated[str | None, Form()] = None,
    accent: Annotated[str, Form()] = "north",
) -> JSONResponse:
    payload = await audio.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, detail={"code": "audio_too_large", "message": "Keep the recording under 10 MB."}
        )
    try:
        result = analyze_recording(
            payload,
            word_id=word,
            intended_tone=intended_tone,
            accent=accent,
        )
        return JSONResponse(result)
    except SignalQualityError as error:
        return JSONResponse(
            status_code=422,
            content={"detail": {**error.as_dict(), "needs_retry": True}},
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


def _sentence(sentence_id: str) -> dict[str, Any]:
    item = next(
        (entry for entry in echo_document().get("sentences", []) if entry.get("id") == sentence_id),
        None,
    )
    if item is None:
        raise HTTPException(
            404, detail={"code": "unknown_sentence", "message": "Choose a seeded Echo sentence."}
        )
    return item


def _ai_explanation(target: str, transcript: str, diff: list[dict[str, Any]], fallback: str) -> str:
    key = openai_api_key()
    if not key or all(item.get("kind") == "match" for item in diff):
        return fallback
    try:
        client = OpenAI(api_key=key, timeout=AI_TIMEOUT_SECONDS, max_retries=0)
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
            max_output_tokens=100,
        )
        return response.output_parsed.explanation if response.output_parsed else fallback
    except Exception:
        return fallback


def _generate_reveal(reveal_id: str, explanation: str) -> None:
    key = openai_api_key()
    if not key:
        return
    try:
        client = OpenAI(api_key=key, timeout=120, max_retries=0)
        result = client.images.generate(
            model=IMAGE_MODEL,
            prompt=(
                "Flat 2D minimal illustration, warm palette on near-black, single "
                "centered subject, "
                "no text, no border. Illustrate this playful literal Vietnamese misunderstanding: "
                + explanation
            ),
            size="1024x1024",
            quality="medium",
            output_format="png",
            n=1,
        )
        data = base64.b64decode(result.data[0].b64_json)
        with REVEAL_LOCK:
            REVEAL_CACHE[reveal_id] = {"status": "ready", "image": data}
    except Exception:
        with REVEAL_LOCK:
            REVEAL_CACHE[reveal_id] = {"status": "failed"}


@router.post("/echo/transcribe")
async def echo_transcribe(
    background_tasks: BackgroundTasks,
    sentence_id: Annotated[str, Form()],
    demo_id: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    sentence = _sentence(sentence_id)
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
        if demo is None or demo.get("sentence_id") != sentence_id:
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
        client = OpenAI(api_key=key, timeout=30, max_retries=0)
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
        reveal_id = hashlib.sha256(
            f"{sentence_id}:{normalize_text(transcript)}".encode()
        ).hexdigest()[:16]
        with REVEAL_LOCK:
            status = REVEAL_CACHE.setdefault(reveal_id, {"status": "pending"})
        if status.get("status") == "pending":
            background_tasks.add_task(_generate_reveal, reveal_id, explanation)
    return {
        "sentence_id": sentence_id,
        "target": sentence["text"],
        "transcript": normalize_text(transcript),
        "diff": diff,
        "explanation": explanation,
        "source": source,
        "reveal_id": reveal_id,
    }


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
    _sentence(sentence_id)
    if accent not in {"north", "south"}:
        raise HTTPException(404, detail="Unknown accent")
    return FileResponse(
        _resolve_repo_file(f"targets/echo/{accent}/{sentence_id}.wav"),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/echo/speak")
def echo_speak(request: EchoSpeakRequest) -> Response:
    if request.sentence_id:
        item = _sentence(request.sentence_id)
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
