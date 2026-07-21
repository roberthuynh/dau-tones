"""FastAPI application for local development and the Vercel Python service."""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import logging
import re
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
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
from .errors import RouteError
from .guards import (
    COACH_POLICY,
    DRILL_POLICY,
    REVEAL_POLICY,
    SPEAK_POLICY,
    TRANSCRIBE_POLICY,
    GuardDecision,
    GuardIdentity,
    GuardUnavailable,
    LimitPolicy,
    RequestGuard,
    active_guard,
    fallback_guard,
    request_identity,
    signed_client_cookie,
    verified_client_id,
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
    MAX_REQUEST_BYTES,
    MAX_UPLOAD_BYTES,
    REPO_ROOT,
    guard_fail_closed,
    guard_mode,
    has_explicit_client_id_secret,
    has_openai_key,
    has_persistent_guard,
    is_vercel_deployment,
    openai_api_key,
    reveal_signing_secret,
)

logger = logging.getLogger("dau.api")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_REVEAL_ID_PATTERN = re.compile(r"^[a-f0-9]{20}\.[a-f0-9]{24}$")
_CURRICULUM_ID_PATTERN = re.compile(r"^[a-z0-9-]{1,100}$")

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


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message, **(extra or {})}},
        headers=headers,
    )


@app.middleware("http")
async def security_and_request_log(request: Request, call_next: Any) -> Response:
    """Add stable request IDs and log metadata without audio, text, query, or IP data."""

    supplied_id = request.headers.get("x-request-id", "")
    request_id = supplied_id if _REQUEST_ID_PATTERN.fullmatch(supplied_id) else uuid4().hex
    request.state.request_id = request_id
    request.state.guard_backend = "none"
    request.state.guard_outcome = "not_checked"
    request.state.cache_status = "not_applicable"
    request.state.fallback = "none"
    request.state.model_role = "none"
    cookie_value = request.cookies.get("dau_client")
    client_id = verified_client_id(cookie_value)
    new_cookie = None
    if client_id is None:
        new_cookie, client_id = signed_client_cookie()
    request.state.dau_client_id = client_id
    started = time.perf_counter()
    length_header = request.headers.get("content-length", "")
    if length_header.isdigit() and int(length_header) > MAX_REQUEST_BYTES:
        response: Response = _error_response(
            413,
            "request_too_large",
            "Keep this request under 12 MB.",
        )
    else:
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "microphone=(self), camera=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; "
        "frame-ancestors 'none'; form-action 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; "
        "connect-src 'self'; worker-src 'self' blob:; manifest-src 'self'"
    )
    response.headers["Cross-Origin-Resource-Policy"] = "same-site"
    if new_cookie:
        response.set_cookie(
            "dau_client",
            new_cookie,
            max_age=31_536_000,
            httponly=True,
            secure=is_vercel_deployment(),
            samesite="strict",
            path="/",
        )
    route = request.scope.get("route")
    endpoint = getattr(route, "path", "unmatched")
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "endpoint": endpoint,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                "guard": request.state.guard_backend,
                "guard_outcome": request.state.guard_outcome,
                "cache": request.state.cache_status,
                "fallback": request.state.fallback,
                "model_role": request.state.model_role,
            },
            separators=(",", ":"),
        )
    )
    return response


router = APIRouter()


class EchoExplanation(BaseModel):
    explanation: str = Field(min_length=4, max_length=220)


def _guard_headers(decision: GuardDecision) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "Retry-After": str(decision.retry_after),
    }


@dataclass
class _GuardLease:
    guard: RequestGuard
    policy: LimitPolicy
    identity: GuardIdentity
    decision: GuardDecision

    def release(self) -> None:
        try:
            self.guard.release(self.policy, self.identity, self.decision.lease_token)
        except GuardUnavailable:
            logger.warning("Could not release model lease policy=%s", self.policy.name)


def _require_paid_boundary(request: Request) -> None:
    if not is_vercel_deployment():
        return
    if request.headers.get("x-dau-bot-verified") != "1":
        raise RouteError(
            403,
            "bot_blocked",
            "Please retry this AI feature from the Dấu app.",
        )
    if guard_mode() == "strict" and (
        not has_persistent_guard() or not has_explicit_client_id_secret()
    ):
        raise RouteError(
            503,
            "ai_guard_unavailable",
            "This AI feature is temporarily unavailable. The offline lesson still works.",
        )


def _guard_call(
    request: Request, policy: LimitPolicy, operation: str
) -> tuple[RequestGuard, GuardIdentity, GuardDecision]:
    guard = active_guard()
    identity = request_identity(request)
    try:
        if operation == "window":
            decision = guard.check_window(policy, identity)
        elif operation == "client_day":
            decision = guard.acquire_client_day(policy, identity)
        else:
            decision = guard.acquire_model(policy, identity)
    except GuardUnavailable as error:
        if (is_vercel_deployment() and guard_mode() == "strict") or guard_fail_closed():
            raise RouteError(
                503,
                "ai_guard_unavailable",
                "This AI feature is briefly unavailable. The offline lesson still works.",
            ) from error
        guard = fallback_guard()
        if operation == "window":
            decision = guard.check_window(policy, identity)
        elif operation == "client_day":
            decision = guard.acquire_client_day(policy, identity)
        else:
            decision = guard.acquire_model(policy, identity)
    request.state.guard_backend = decision.backend
    request.state.guard_outcome = decision.reason
    if not decision.allowed:
        if decision.reason == "disabled":
            raise RouteError(
                503,
                "ai_paused",
                "AI features are paused. The complete offline lesson still works.",
            )
        if decision.reason.endswith("_daily"):
            code = "ai_daily_limit"
            message = "This AI feature reached its daily cap. The offline lesson still works."
        elif decision.reason.endswith("_concurrency"):
            code = "ai_busy"
            message = "This AI feature is busy with another take. Try again in a moment."
        else:
            code = "ai_rate_limited"
            message = "That feature has had enough requests for now. Try again shortly."
        raise RouteError(
            429,
            code,
            message,
            headers=_guard_headers(decision),
            extra={"retry_after": decision.retry_after},
        )
    return guard, identity, decision


def _check_window(request: Request, policy: LimitPolicy, *, paid: bool) -> None:
    if paid:
        _require_paid_boundary(request)
    _guard_call(request, policy, "window")


def _acquire_model(request: Request, policy: LimitPolicy) -> _GuardLease:
    guard, identity, decision = _guard_call(request, policy, "model")
    return _GuardLease(guard, policy, identity, decision)


def _check_client_day(request: Request, policy: LimitPolicy) -> None:
    _guard_call(request, policy, "client_day")


def _cache_key(namespace: str, payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    return f"dau:cache:{namespace}:v1:{digest}"


def _cache_get(request: Request, key: str) -> str | None:
    try:
        value = active_guard().get(key)
    except GuardUnavailable:
        request.state.cache_status = "error"
        return None
    request.state.cache_status = "hit" if value is not None else "miss"
    return value


def _cache_set(request: Request, key: str, value: str, ttl_seconds: int) -> None:
    try:
        active_guard().set(key, value, ttl_seconds)
    except GuardUnavailable:
        request.state.cache_status = "write_error"


def _openai_client(key: str, *, timeout: float) -> Any:
    """Keep the optional OpenAI SDK off the local DSP import path."""

    from openai import OpenAI

    return OpenAI(api_key=key, timeout=timeout, max_retries=0)


def _upstream_route_error(error: Exception, message: str) -> RouteError:
    if "timeout" in type(error).__name__.lower():
        return RouteError(
            504,
            "upstream_timeout",
            message,
            headers={"Retry-After": "2"},
        )
    return RouteError(502, "upstream_failed", message)


def _validated_audio_duration(payload: bytes) -> float:
    """Reject corrupt uploads and enforce exact duration bounds for WAV takes."""

    duration = 1.0
    if payload.startswith(b"RIFF") and payload[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(payload), "rb") as recording:
                sample_rate = recording.getframerate()
                if sample_rate <= 0:
                    raise ValueError("invalid sample rate")
                duration = recording.getnframes() / sample_rate
        except (EOFError, ValueError, wave.Error) as error:
            raise RouteError(
                422,
                "invalid_audio",
                "Dấu could not decode that recording. Try one clear Dialogue line.",
            ) from error
    elif len(payload) < 64 or not (
        payload.startswith(b"\x1aE\xdf\xa3")
        or payload.startswith(b"OggS")
        or payload[4:8] == b"ftyp"
    ):
        raise RouteError(
            422,
            "invalid_audio",
            "Dấu could not decode that recording. Try one clear Dialogue line.",
        )
    if duration < 0.35:
        raise RouteError(
            422,
            "audio_too_short",
            "Keep speaking for at least a third of a second.",
        )
    if duration > 30.0:
        raise RouteError(
            422,
            "audio_too_long",
            "Keep one Dialogue take under 30 seconds.",
        )
    return duration


def warm_analysis_runtime(timing: dict[str, float]) -> bool:
    """Load the pitch stack only when the compatibility warmup is explicitly called."""

    from .analysis_service import warm_analysis_runtime as warm

    return warm(timing)


def _health() -> dict[str, Any]:
    key = has_openai_key()
    paid_guard_ready = not (
        is_vercel_deployment()
        and guard_mode() == "strict"
        and (not has_persistent_guard() or not has_explicit_client_id_secret())
    )
    live_ready = key and paid_guard_ready
    modes = public_words().get("scoring_modes", {"north": "four_family", "south": "four_family"})
    return {
        "status": "ok",
        "ready": True,
        "reference_corpus_validated": reference_corpus_is_complete(),
        "scoring_modes": modes,
        "capabilities": {
            "local_dsp": True,
            "ai_coaching": live_ready,
            "generated_drills": live_ready,
            "live_echo_transcription": live_ready,
            "live_echo_art": live_ready,
            "cached_echo_speech": True,
            "paid_guard_ready": paid_guard_ready,
        },
        "request_guard": "persistent" if has_persistent_guard() else "local",
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
    if is_vercel_deployment():
        raise RouteError(
            503,
            "server_analysis_unavailable",
            "Production tone analysis runs locally in your browser.",
        )
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
    if is_vercel_deployment():
        raise RouteError(
            503,
            "server_analysis_unavailable",
            "Production tone analysis runs locally in your browser.",
        )
    from . import analysis_service

    payload = await audio.read(MAX_UPLOAD_BYTES + 1)
    if len(payload) > MAX_UPLOAD_BYTES:
        raise RouteError(413, "audio_too_large", "Keep the recording under 10 MB.")
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
        raise RouteError(400, "invalid_request", str(error)) from error


@router.post("/coach")
def coaching(payload: CoachRequest, request: Request) -> dict[str, Any]:
    if not has_openai_key():
        request.state.fallback = "rules_no_key"
        return coach(payload).model_dump()
    request.state.model_role = "coach"
    _check_window(request, COACH_POLICY, paid=True)
    cache_key = _cache_key("coach", payload.model_dump(mode="json"))
    cached = _cache_get(request, cache_key)
    if cached is not None:
        cached_result = cast(dict[str, Any], json.loads(cached))
        cached_result["refinement_status"] = "cache_hit"
        return cached_result
    lease = _acquire_model(request, COACH_POLICY)
    try:
        result = coach(payload, safety_identifier=request_identity(request).client).model_dump()
    finally:
        lease.release()
    if result.get("source") == "gpt-5.6-sol":
        _cache_set(request, cache_key, json.dumps(result, ensure_ascii=False), 6 * 3600)
    else:
        request.state.fallback = "rules_provider"
    return result


@router.post("/drills/generate")
def drills(payload: DrillRequest, request: Request) -> dict[str, Any]:
    if not has_openai_key():
        request.state.fallback = "rules_no_key"
        return generate_drill(payload)
    request.state.model_role = "drill"
    _check_window(request, DRILL_POLICY, paid=True)
    cache_key = _cache_key("drill", payload.model_dump(mode="json"))
    cached = _cache_get(request, cache_key)
    if cached is not None:
        return cast(dict[str, Any], json.loads(cached))
    lease = _acquire_model(request, DRILL_POLICY)
    try:
        result = generate_drill(payload, safety_identifier=request_identity(request).client)
    finally:
        lease.release()
    if result.get("source") == "gpt-5.6-sol":
        _cache_set(request, cache_key, json.dumps(result, ensure_ascii=False), 24 * 3600)
    else:
        request.state.fallback = "rules_provider"
    return result


def _resolve_repo_file(relative_path: str) -> Path:
    candidate = (REPO_ROOT / relative_path).resolve()
    if REPO_ROOT not in candidate.parents or not candidate.is_file():
        raise RouteError(
            404,
            "asset_missing",
            "That committed sample is unavailable.",
        )
    return candidate


@router.get("/targets/{accent}/{word_id}.wav")
def target_audio(accent: str, word_id: str) -> FileResponse:
    if accent not in {"north", "south"}:
        raise RouteError(404, "unknown_accent", "Choose the Northern or Southern voice.")
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
        raise RouteError(404, "unknown_demo", "That committed demo is unavailable.")
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
        raise RouteError(
            404,
            "unknown_sentence",
            "Choose a seeded Echo dialogue line.",
        )
    return cast(dict[str, Any], item)


def _offline_demo(demo_id: str) -> dict[str, Any] | None:
    for scene in echo_document().get("scenes", []):
        demo = scene.get("offline_demo", {})
        if demo.get("id") == demo_id:
            return {**demo, "scene_id": scene["id"]}
    return None


def _bounded_text(value: Any, limit: int = 600) -> str:
    return str(value).strip()[:limit]


def _sanitized_diff(diff: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only curated alignment evidence needed by the explanation model."""

    string_fields = {
        "target",
        "heard",
        "kind",
        "target_tone",
        "heard_tone",
        "semantic_status",
        "meaning_explanation",
    }
    sanitized: list[dict[str, Any]] = []
    for item in diff[:64]:
        sanitized.append(
            {
                key: (_bounded_text(value, 180) if isinstance(value, str) else value)
                for key, value in item.items()
                if key in string_fields and (isinstance(value, str) or value is None)
            }
        )
    return sanitized


def _ai_explanation(
    diff: list[dict[str, Any]], fallback: str, safety_identifier: str | None = None
) -> str:
    key = openai_api_key()
    if not key or all(item.get("kind") == "match" for item in diff):
        return fallback
    try:
        client = _openai_client(key, timeout=AI_TIMEOUT_SECONDS)
        arguments: dict[str, Any] = {
            "model": TEXT_MODEL,
            "reasoning": {"effort": "low"},
            "text": {"verbosity": "low"},
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Explain the literal meaning created by these Vietnamese changed "
                        "tokens in one accurate, playful sentence. Use only supplied curated "
                        "meanings; do not invent one."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "changed_tokens": _sanitized_diff(
                                [item for item in diff if item.get("kind") != "match"]
                            ),
                            "fallback": _bounded_text(fallback, 300),
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text_format": EchoExplanation,
            "max_output_tokens": 400,
            "store": False,
        }
        if safety_identifier:
            arguments["safety_identifier"] = safety_identifier
        response = client.responses.parse(**arguments)
        return response.output_parsed.explanation if response.output_parsed else fallback
    except Exception:
        return fallback


def _reveal_cache_id(explanation: str) -> str:
    message = f"echo-reveal-v2:{normalize_text(explanation)}".encode()
    return hmac.new(reveal_signing_secret().encode(), message, hashlib.sha256).hexdigest()[:24]


def _issue_reveal_permit(request: Request, explanation: str) -> str | None:
    identity = request_identity(request)
    image_id = _reveal_cache_id(explanation)
    nonce = uuid4().hex[:20]
    signature = hmac.new(
        reveal_signing_secret().encode(),
        f"{nonce}:{image_id}:{identity.client}:{identity.network}".encode(),
        hashlib.sha256,
    ).hexdigest()[:24]
    permit_id = f"{nonce}.{signature}"
    record = json.dumps(
        {
            "image_id": image_id,
            "client": identity.client,
            "network": identity.network,
            "explanation": _bounded_text(explanation, 220),
        },
        separators=(",", ":"),
    )
    try:
        active_guard().set(f"dau:permit:reveal:v1:{permit_id}", record, 15 * 60)
    except GuardUnavailable:
        return None
    return permit_id


def _read_reveal_permit(request: Request, permit_id: str) -> tuple[str, str] | None:
    try:
        encoded = active_guard().get(f"dau:permit:reveal:v1:{permit_id}")
    except GuardUnavailable as error:
        raise RouteError(
            503,
            "ai_guard_unavailable",
            "Live meaning art is briefly unavailable. The text feedback still works.",
        ) from error
    if encoded is None:
        return None
    try:
        record = json.loads(encoded)
    except json.JSONDecodeError:
        return None
    identity = request_identity(request)
    image_id = record.get("image_id")
    explanation = record.get("explanation")
    if (
        not isinstance(image_id, str)
        or not isinstance(explanation, str)
        or image_id != _reveal_cache_id(explanation)
        or record.get("client") != identity.client
        or record.get("network") != identity.network
    ):
        return None
    nonce, separator, signature = permit_id.partition(".")
    expected = hmac.new(
        reveal_signing_secret().encode(),
        f"{nonce}:{image_id}:{identity.client}:{identity.network}".encode(),
        hashlib.sha256,
    ).hexdigest()[:24]
    if not separator or not hmac.compare_digest(signature, expected):
        return None
    return image_id, explanation


def _finish_reveal_permit(permit_id: str) -> None:
    try:
        active_guard().consume(f"dau:permit:reveal:v1:{permit_id}")
    except GuardUnavailable:
        logger.warning("Could not consume completed reveal permit")


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
            "Vietnamese misunderstanding: " + _bounded_text(explanation, 220)
        ),
        size="1024x1024",
        quality="medium",
        output_format="webp",
        output_compression=70,
        n=1,
    )
    encoded = result.data[0].b64_json
    if not encoded:
        raise RuntimeError("The image model returned no image data")
    image = base64.b64decode(encoded)
    if len(image) > 2 * 1024 * 1024:
        raise RuntimeError("The image model returned an oversized image")
    return image


@router.post("/echo/transcribe", response_model=EchoTranscribeResponse)
async def echo_transcribe(
    request: Request,
    turn_id: Annotated[str | None, Form()] = None,
    sentence_id: Annotated[str | None, Form()] = None,
    demo_id: Annotated[str | None, Form()] = None,
    audio: Annotated[UploadFile | None, File()] = None,
) -> dict[str, Any]:
    if turn_id and sentence_id:
        raise RouteError(
            400,
            "invalid_request",
            "Send either turn_id or sentence_id, not both.",
        )
    if demo_id and audio is not None:
        raise RouteError(
            400,
            "invalid_request",
            "A committed demo cannot be combined with a new recording.",
        )
    if any(
        value is not None and not _CURRICULUM_ID_PATTERN.fullmatch(value)
        for value in (turn_id, sentence_id, demo_id)
    ):
        raise RouteError(400, "invalid_request", "Choose a valid committed Dialogue item.")
    if demo_id is None:
        _check_window(request, TRANSCRIBE_POLICY, paid=True)
    requested_id = turn_id or sentence_id
    if not requested_id:
        raise RouteError(
            400,
            "missing_turn",
            "Choose a dialogue line to practice.",
        )
    sentence = _echo_entry(requested_id)
    if sentence.get("speaker") not in {None, "learner"}:
        raise RouteError(
            400,
            "learner_turn_required",
            "Choose one of the learner lines to practice.",
        )
    resolved_turn_id = sentence["id"]
    source = "fixture"
    transcript: str
    lease: _GuardLease | None = None
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
            raise RouteError(404, "unknown_demo", "That Echo demo is unavailable.")
        transcript = demo["committed_transcript"]
    else:
        key = openai_api_key()
        if not key:
            raise RouteError(
                503,
                "echo_live_requires_key",
                (
                    "Live transcript feedback needs an OpenAI key. Your recording still "
                    "stays available for replay and shadowing."
                ),
            )
        if audio is None:
            raise RouteError(400, "missing_audio", "Record the sentence first.")
        payload = await audio.read(MAX_UPLOAD_BYTES + 1)
        if len(payload) > MAX_UPLOAD_BYTES:
            raise RouteError(
                413,
                "audio_too_large",
                "Keep the recording under 10 MB.",
            )
        allowed_media_types = {
            "audio/webm",
            "audio/ogg",
            "audio/mp4",
            "audio/wav",
            "audio/x-wav",
        }
        if audio.content_type not in allowed_media_types:
            raise RouteError(
                415,
                "unsupported_audio_type",
                "Record WebM, Ogg, MP4, or WAV audio.",
            )
        media_type = audio.content_type
        await run_in_threadpool(_validated_audio_duration, payload)
        request.state.model_role = "transcription_and_explanation"
        lease = _acquire_model(request, TRANSCRIBE_POLICY)
        client = _openai_client(key, timeout=AI_TIMEOUT_SECONDS)
        extension = {
            "audio/ogg": "ogg",
            "audio/mp4": "m4a",
            "audio/wav": "wav",
            "audio/x-wav": "wav",
        }.get(media_type, "webm")
        try:
            result = await run_in_threadpool(
                client.audio.transcriptions.create,
                model=TRANSCRIPTION_MODEL,
                file=(f"echo.{extension}", payload, media_type),
                language="vi",
                prompt=(
                    "Transcribe exactly what was heard in Vietnamese NFC. Preserve the "
                    "speaker's tone marks. Do not silently correct a wrong tone to this "
                    "target: " + _bounded_text(sentence["text"])
                ),
                response_format="text",
            )
        except Exception as error:
            lease.release()
            raise _upstream_route_error(
                error,
                "Dấu could not read this take. Your recording is still available for replay.",
            ) from error
        try:
            transcript = result if isinstance(result, str) else result.text
        except Exception as error:
            lease.release()
            raise _upstream_route_error(
                error,
                "Dấu could not read this take. Your recording is still available for replay.",
            ) from error
        source = TRANSCRIPTION_MODEL
    try:
        diff = align_transcript(sentence["text"], transcript)
        fallback = literal_explanation(diff)
        explanation = (
            await run_in_threadpool(
                _ai_explanation,
                diff,
                fallback,
                request_identity(request).client,
            )
            if lease is not None
            else fallback
        )
    finally:
        if lease is not None:
            lease.release()
    reveal_id = None
    if lease is not None and any(item.get("kind") != "match" for item in diff):
        reveal_id = _issue_reveal_permit(request, fallback)
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
def generate_echo_reveal(
    reveal_id: str,
    request: Request,
) -> Response:
    """Return one reveal directly so serverless instance changes cannot strand polling."""

    if not _REVEAL_ID_PATTERN.fullmatch(reveal_id):
        raise RouteError(
            400,
            "invalid_reveal",
            "That one-time reveal has expired or no longer matches this feedback.",
        )
    _check_window(request, REVEAL_POLICY, paid=True)
    if not has_openai_key():
        raise RouteError(
            503,
            "reveal_requires_key",
            "The text feedback is ready, but live meaning art needs an OpenAI key.",
        )
    permit = _read_reveal_permit(request, reveal_id)
    if permit is None:
        raise RouteError(
            400,
            "invalid_reveal",
            "That one-time reveal has expired or no longer matches this feedback.",
        )
    image_id, explanation = permit
    request.state.model_role = "meaning_art"

    persistent_key = f"dau:cache:reveal:v1:{image_id}"
    persisted = _cache_get(request, persistent_key)
    if persisted is not None:
        try:
            data = base64.b64decode(persisted, validate=True)
        except ValueError:
            data = b""
        if data:
            _finish_reveal_permit(reveal_id)
            return Response(
                data,
                media_type="image/webp",
                headers={"Cache-Control": "public, max-age=86400", "ETag": f'"{image_id}"'},
            )

    lease = _acquire_model(request, REVEAL_POLICY)
    try:
        # A previous instance may have filled the cache while this request waited
        # for the global image lease.
        persisted = _cache_get(request, persistent_key)
        data = base64.b64decode(persisted, validate=True) if persisted else b""
        if not data:
            data = _generate_reveal(explanation)
            _cache_set(
                request,
                persistent_key,
                base64.b64encode(data).decode("ascii"),
                24 * 3600,
            )
    except RouteError:
        raise
    except Exception as error:
        raise _upstream_route_error(
            error,
            "The literal meaning picture is unavailable. The text feedback still works.",
        ) from error
    finally:
        lease.release()
    _finish_reveal_permit(reveal_id)

    return Response(
        data,
        media_type="image/webp",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{image_id}"',
        },
    )


@router.get("/echo/speak/{accent}/{sentence_id}.wav")
def seeded_echo_speech(accent: str, sentence_id: str, request: Request) -> FileResponse:
    _check_window(request, SPEAK_POLICY, paid=False)
    _check_client_day(request, SPEAK_POLICY)
    _echo_entry(sentence_id)
    if accent not in {"north", "south"}:
        raise RouteError(404, "unknown_accent", "Choose the Northern or Southern voice.")
    return FileResponse(
        _resolve_repo_file(f"targets/echo/{accent}/{sentence_id}.wav"),
        media_type="audio/wav",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


@router.post("/echo/speak")
def echo_speak(payload: EchoSpeakRequest, request: Request) -> Response:
    _check_window(request, SPEAK_POLICY, paid=False)
    _check_client_day(request, SPEAK_POLICY)
    requested_id = payload.turn_id or payload.sentence_id
    if requested_id:
        item = _echo_entry(requested_id)
        path = REPO_ROOT / item["shadow_audio"][payload.accent]
        if path.is_file():
            return FileResponse(
                path,
                media_type="audio/wav",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
        raise RouteError(
            404,
            "speech_unavailable",
            "That committed shadowing take is unavailable.",
        )
    raise RouteError(
        400,
        "missing_turn",
        "Choose a committed dialogue line to shadow.",
    )


app.include_router(router)
# Local Vite strips /api while Vercel may preserve a service route prefix. Both
# paths are served from the same handlers, without duplicating OpenAPI entries.
app.include_router(router, prefix="/api", include_in_schema=False)


@app.exception_handler(RouteError)
async def route_error(_request: Request, error: RouteError) -> JSONResponse:
    return _error_response(
        error.status_code,
        error.code,
        error.message,
        headers=error.headers,
        extra=error.extra,
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(_request: Request, error: RequestValidationError) -> JSONResponse:
    issues = [
        {
            "location": [str(part) for part in item.get("loc", ())],
            "message": str(item.get("msg", "Invalid value"))[:180],
            "type": str(item.get("type", "validation_error"))[:80],
        }
        for item in error.errors()[:12]
    ]
    return _error_response(
        422,
        "invalid_request",
        "Check the request fields and try again.",
        extra={"issues": issues},
    )


@app.exception_handler(HTTPException)
async def http_error(_request: Request, error: HTTPException) -> JSONResponse:
    detail = error.detail
    if isinstance(detail, dict):
        code = str(detail.get("code", "request_failed"))
        message = str(detail.get("message", "The request could not be completed."))
        extra = {key: value for key, value in detail.items() if key not in {"code", "message"}}
    else:
        code = "not_found" if error.status_code == 404 else "request_failed"
        message = str(detail) if isinstance(detail, str) else "The request could not be completed."
        extra = None
    return _error_response(
        error.status_code,
        code,
        message,
        headers=dict(error.headers or {}),
        extra=extra,
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, error: Exception) -> JSONResponse:
    route = request.scope.get("route")
    logger.error(
        "Unhandled request error request_id=%s endpoint=%s",
        getattr(request.state, "request_id", "unknown"),
        getattr(route, "path", "unmatched"),
    )
    return _error_response(
        500,
        "server_error",
        "Dấu hit an unexpected error. Try once more.",
    )
