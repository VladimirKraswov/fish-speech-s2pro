from __future__ import annotations

import base64
from contextlib import asynccontextmanager
import json
import logging
import time
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, Response, StreamingResponse
import httpx

from .audio import pcm_payload, streaming_wav_header, wav_info
from .runtime import SGLangS2Runtime
from .settings import load_settings

logger = logging.getLogger(__name__)

settings = load_settings()
runtime = SGLangS2Runtime(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.startup()
    yield
    await runtime.shutdown()


app = FastAPI(
    title="tts-sglang-s2",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.exception_handler(ValueError)
async def value_error(_, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error(_, exc: RuntimeError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/healthz")
async def healthz():
    status = await runtime.status()
    if not status["ready"]:
        raise HTTPException(status_code=503, detail=status.get("detail") or "SGLang S2 runtime is not ready")
    return {"status": "ok", **status}


@app.get("/health")
async def health():
    return await healthz()


@app.get("/internal/status")
async def status():
    return await runtime.status()


@app.get("/v1/models")
async def models():
    return {
        "object": "list",
        "data": [
            {
                "id": settings.model_name,
                "object": "model",
                "created": 0,
                "owned_by": "sglang-omni",
                "root": settings.model_name,
            }
        ],
    }


@app.post("/internal/synthesize")
async def internal_synthesize(payload: dict[str, Any]):
    if not runtime.ready:
        _ensure_ready(await runtime.status())
    audio, media_type = await runtime.synthesize(payload)
    return Response(content=audio, media_type=media_type)


@app.post("/internal/stream")
async def internal_stream(payload: dict[str, Any]):
    if not runtime.ready:
        _ensure_ready(await runtime.status())
    client, response = await runtime.open_sse_stream({**payload, "response_format": "wav"})
    headers = {
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
        "X-Target-First-Byte-Ms": str(settings.target_first_byte_ms),
        "X-Early-Wav-Header": "1" if settings.early_wav_header else "0",
    }
    return StreamingResponse(
        _sse_to_wav_stream(client, response),
        media_type="audio/wav",
        headers=headers,
    )


@app.get("/internal/stream")
async def internal_stream_get(
    text: str = Query(...),
    reference_id: str | None = None,
    max_new_tokens: int | None = None,
):
    payload: dict[str, Any] = {"text": text}
    if reference_id:
        payload["reference_id"] = reference_id
    if max_new_tokens is not None:
        payload["max_new_tokens"] = max_new_tokens
    return await internal_stream(payload)


@app.post("/v1/audio/speech")
async def v1_audio_speech(payload: dict[str, Any]):
    if not runtime.ready:
        _ensure_ready(await runtime.status())
    stream = bool(payload.get("stream"))
    if stream:
        client, response = await runtime.open_sse_stream(payload)
        return StreamingResponse(
            _relay_response(client, response),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    audio, media_type = await runtime.synthesize(payload)
    return Response(content=audio, media_type=media_type)


async def _relay_response(client: httpx.AsyncClient, response: httpx.Response) -> AsyncIterator[bytes]:
    try:
        async for chunk in response.aiter_bytes():
            if chunk:
                yield chunk
    finally:
        await response.aclose()
        await client.aclose()


async def _sse_to_wav_stream(client: httpx.AsyncClient, response: httpx.Response) -> AsyncIterator[bytes]:
    started = time.perf_counter()
    first_audio_ms: float | None = None
    header_sent = False

    try:
        if settings.early_wav_header:
            yield streaming_wav_header(
                sample_rate=settings.stream_sample_rate,
                channels=settings.stream_channels,
                bits_per_sample=settings.stream_bits_per_sample,
            )
            header_sent = True

        async for line in response.aiter_lines():
            data = _sse_data(line)
            if data is None:
                continue
            if data == "[DONE]":
                break

            chunk = _decode_sse_audio(data)
            if not chunk:
                continue

            if first_audio_ms is None:
                first_audio_ms = (time.perf_counter() - started) * 1000
                logger.info("SGLang S2 first upstream audio chunk in %.1f ms", first_audio_ms)

            info = wav_info(chunk)
            if not header_sent:
                if info is None:
                    yield streaming_wav_header(
                        sample_rate=settings.stream_sample_rate,
                        channels=settings.stream_channels,
                        bits_per_sample=settings.stream_bits_per_sample,
                    )
                    yield chunk
                else:
                    yield streaming_wav_header(
                        sample_rate=info.sample_rate,
                        channels=info.channels,
                        bits_per_sample=info.bits_per_sample,
                    )
                    yield info.payload
                header_sent = True
                continue

            payload = pcm_payload(chunk)
            if payload:
                yield payload
    finally:
        await response.aclose()
        await client.aclose()


def _ensure_ready(status: dict[str, Any]) -> None:
    if not status["ready"]:
        raise HTTPException(status_code=503, detail=status.get("detail") or "SGLang S2 runtime is not ready")


def _sse_data(line: str) -> str | None:
    if not line or not line.startswith("data:"):
        return None
    return line[len("data:") :].strip()


def _decode_sse_audio(data: str) -> bytes | None:
    if data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    audio = payload.get("audio") or {}
    b64 = audio.get("data") if isinstance(audio, dict) else None
    if not b64:
        return None
    return base64.b64decode(b64)
