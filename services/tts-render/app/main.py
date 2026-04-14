import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response

from .runtime import create_runtime
from .settings import load_settings

settings = load_settings()
runtime = create_runtime(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.startup()
    yield
    await runtime.shutdown()

app = FastAPI(title="tts-render", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    status = runtime.status()
    if not status["ready"]:
        raise HTTPException(status_code=503, detail=status.get("detail") or "Render runtime is not ready")
    return {
        "status": "ok",
        "ready": status["ready"],
        "engine": status.get("engine", settings.render_engine),
        "detail": status.get("detail", ""),
    }


@app.get("/internal/status")
async def status():
    return runtime.status()


@app.post("/internal/synthesize")
async def synthesize(payload: dict):
    if not runtime.status()["ready"]:
        raise HTTPException(status_code=503, detail="Render runtime is not ready")
    if not str(payload.get("text", "")).strip():
        raise HTTPException(status_code=400, detail="Text must not be empty")

    try:
        audio = await asyncio.to_thread(runtime.synthesize, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(content=audio, media_type="audio/wav")


@app.post("/internal/activate")
async def activate(payload: dict):
    path = payload.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="Model path is required")
    try:
        return await runtime.switch_model(path)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
