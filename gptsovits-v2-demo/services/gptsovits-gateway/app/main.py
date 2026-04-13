from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging

import httpx
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from .reference_store import ReferenceStore
from .settings import Settings, load_settings


ALLOWED_LANGUAGES = {
    "en": {"value": "en", "label": "English"},
    "zh": {"value": "zh", "label": "Chinese"},
}
logger = logging.getLogger("gptsovits-gateway")

settings: Settings = load_settings()
references = ReferenceStore(
    settings.references_root,
    max_seconds=settings.reference_max_seconds,
    sample_rate=settings.reference_sample_rate,
    channels=settings.reference_channels,
)


class SynthesisRequest(BaseModel):
    text: str
    reference_id: str | None = None
    text_lang: str = "en"
    prompt_text: str | None = None
    prompt_lang: str | None = None
    speed_factor: float = 1.0
    text_split_method: str = "cut5"
    top_k: int = 5
    top_p: float = 1.0
    temperature: float = 1.0


def normalize_language(value: str | None, label: str) -> str:
    language = (value or "").strip().lower()
    if language not in ALLOWED_LANGUAGES:
        raise ValueError(f"{label} must be one of: {', '.join(ALLOWED_LANGUAGES)}")
    return language


async def probe_runtime(client: httpx.AsyncClient) -> dict:
    try:
        # Probe the runtime with an empty POST so FastAPI validation returns 422
        # before the upstream handler touches missing query params and raises 500.
        response = await client.post(f"{settings.runtime_url}/tts", json={}, timeout=10.0)
    except httpx.RequestError as exc:
        return {"status": "starting", "ready": False, "detail": str(exc)}

    if response.status_code in {400, 422}:
        return {"status": "ok", "ready": True, "detail": "GPT-SoVITS runtime is responding."}
    return {"status": "starting", "ready": False, "detail": f"Unexpected status code: {response.status_code}"}


def status_payload(runtime: dict) -> dict:
    return {
        "status": "ok" if runtime.get("ready") else "starting",
        "ready": bool(runtime.get("ready")),
        "runtime": runtime,
        "default_reference": settings.default_reference_name,
        "default_target_text": settings.default_target_text,
        "languages": list(ALLOWED_LANGUAGES.values()),
        "references": references.list(),
    }


def extract_runtime_error(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return (response.text or f"GPT-SoVITS runtime returned HTTP {response.status_code}").strip()

    if isinstance(data, dict):
        exception = data.get("Exception")
        detail = data.get("detail")
        message = data.get("message")
        if exception:
            if message and str(message).strip() and str(message).strip().lower() != str(exception).strip().lower():
                return f"{exception} (runtime message: {message})"
            return str(exception)
        for key in ("detail", "message"):
            value = data.get(key)
            if value:
                return str(value)
        return str(data)
    return str(data)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    await asyncio.to_thread(
        references.create_demo,
        settings.default_reference_name,
        settings.default_reference_text,
        language=settings.default_reference_language,
        voice=settings.default_reference_voice,
    )
    app.state.http = httpx.AsyncClient(follow_redirects=True)
    try:
        yield
    finally:
        await app.state.http.aclose()


app = FastAPI(title="gptsovits-gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
api = APIRouter(prefix="/api")


@app.exception_handler(ValueError)
async def handle_value_error(_, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/healthz")
async def healthz():
    runtime = await probe_runtime(app.state.http)
    return {
        "status": "ok" if runtime.get("ready") else "starting",
        "ready": bool(runtime.get("ready")),
        "runtime": runtime,
        "default_reference": settings.default_reference_name,
    }


@api.get("/status")
async def get_status():
    runtime = await probe_runtime(app.state.http)
    return status_payload(runtime)


@api.get("/references")
async def list_references():
    return {"references": references.list()}


@api.get("/events")
async def noop_events():
    return Response(status_code=204)


@api.get("/references/{name}")
async def get_reference(name: str):
    return references.get(name)


@api.get("/references/{name}/audio")
async def get_reference_audio(name: str):
    audio_path = references.audio_path(name)
    if audio_path is None:
        raise ValueError(f"Reference audio does not exist: {name}")
    return FileResponse(audio_path, media_type="audio/wav")


@api.post("/references")
async def upload_reference(
    name: str = Form(...),
    transcript: str = Form(...),
    language: str = Form("en"),
    replace: bool = Form(False),
    audio_file: UploadFile = File(...),
):
    data = await asyncio.to_thread(references.save, name, audio_file, transcript, normalize_language(language, "Reference language"), replace)
    return data


@api.delete("/references/{name}")
async def delete_reference(name: str):
    return await asyncio.to_thread(references.delete, name)


@api.post("/synthesize")
async def synthesize(payload: SynthesisRequest):
    text = payload.text.strip()
    if not text:
        raise ValueError("Text is required.")

    reference_id = payload.reference_id or settings.default_reference_name
    reference = references.get(reference_id)
    audio_path = references.audio_path(reference_id)
    if audio_path is None:
        raise ValueError(f"Reference audio does not exist: {reference_id}")

    prompt_text = (payload.prompt_text or reference["transcript"]).strip()
    if not prompt_text:
        raise ValueError("Prompt text is required.")

    runtime_payload = {
        "text": text,
        "text_lang": normalize_language(payload.text_lang, "Text language"),
        "ref_audio_path": str(audio_path),
        "prompt_text": prompt_text,
        "prompt_lang": normalize_language(payload.prompt_lang or reference["language"], "Prompt language"),
        "media_type": "wav",
        "streaming_mode": False,
        "text_split_method": payload.text_split_method,
        "speed_factor": float(payload.speed_factor),
        "top_k": int(payload.top_k),
        "top_p": float(payload.top_p),
        "temperature": float(payload.temperature),
    }
    payload_preview = {
        "text_lang": runtime_payload["text_lang"],
        "prompt_lang": runtime_payload["prompt_lang"],
        "ref_audio_path": runtime_payload["ref_audio_path"],
        "text_len": len(text),
        "prompt_text_len": len(prompt_text),
        "text_split_method": runtime_payload["text_split_method"],
        "speed_factor": runtime_payload["speed_factor"],
        "top_k": runtime_payload["top_k"],
        "top_p": runtime_payload["top_p"],
        "temperature": runtime_payload["temperature"],
    }

    try:
        response = await app.state.http.post(
            f"{settings.runtime_url}/tts",
            json=runtime_payload,
            timeout=settings.synthesis_timeout_sec,
        )
    except httpx.RequestError as exc:
        raise RuntimeError(f"GPT-SoVITS runtime is unavailable: {exc}") from exc

    if response.status_code != 200:
        detail = extract_runtime_error(response)
        logger.warning(
            "runtime returned non-200 for synthesis: status=%s detail=%s payload=%s",
            response.status_code,
            detail,
            payload_preview,
        )
        raise HTTPException(status_code=502, detail=detail)

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "audio/wav"),
        headers={"Cache-Control": "no-store"},
    )


app.include_router(api)
