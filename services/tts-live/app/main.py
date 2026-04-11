import asyncio
from contextlib import asynccontextmanager
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse

from .audio import pcm_payload
from .runtime import S2CppRuntime
from .settings import load_settings

settings = load_settings()
runtime = S2CppRuntime(settings, str(settings.live_model_path))


def _parts(text: str) -> list[str]:
    raw = " ".join(str(text or "").split())
    if len(raw) <= 56:
        return [raw]
    sentences = [item.strip() for item in re.split(r"(?<=[.!?;:])\s+", raw) if item.strip()]
    if not sentences:
        return [raw]
    first = sentences[0]
    if len(first) > 72:
        return [first[:72].rsplit(" ", 1)[0] or first[:72], first[72:].strip(), *sentences[1:]]
    tail = " ".join(sentences[1:]).strip()
    return [first, tail] if tail else [first]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.startup()
    yield
    await runtime.shutdown()


app = FastAPI(title="tts-live", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    status = runtime.status()
    if not status["ready"]:
        raise HTTPException(status_code=503, detail=status.get("detail") or "Live runtime is not ready")
    return {"status": "ok", "ready": status["ready"], "engine": status["engine"], "detail": status.get("detail", "")}


@app.get("/internal/status")
async def status():
    return runtime.status()


@app.post("/internal/activate")
async def activate(payload: dict):
    path = str(payload.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Model path is required")
    try:
        return await runtime.switch_model(path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/internal/synthesize")
async def synthesize(payload: dict):
    if not runtime.status()["ready"]:
        raise HTTPException(status_code=503, detail="Live runtime is not ready")
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text must not be empty")
    try:
        audio = await asyncio.to_thread(runtime.synthesize, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")


@app.get("/internal/stream/live")
async def stream_live(text: str, reference_id: str | None = None):
    if reference_id:
        raise HTTPException(status_code=409, detail="Live streaming does not support reference conditioning")
    if not runtime.status()["ready"]:
        raise HTTPException(status_code=503, detail="Live runtime is not ready")
    if not str(text or "").strip():
        raise HTTPException(status_code=400, detail="Text must not be empty")

    async def body():
        sent_header = False
        parts = [part for part in _parts(text) if part]
        next_task = asyncio.create_task(asyncio.to_thread(runtime.synthesize, parts[0])) if parts else None
        try:
            for index, _ in enumerate(parts):
                chunk = await next_task
                next_task = None
                if index + 1 < len(parts):
                    next_task = asyncio.create_task(asyncio.to_thread(runtime.synthesize, parts[index + 1]))
                yield chunk if not sent_header else pcm_payload(chunk)
                sent_header = True
        finally:
            if next_task and not next_task.done():
                next_task.cancel()

    return StreamingResponse(
        body(),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
