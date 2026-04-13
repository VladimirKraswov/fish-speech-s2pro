import asyncio
from contextlib import asynccontextmanager
import time

import httpx
from fastapi import FastAPI, APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from shared.events import EventService
from shared.jobs import JobService

from .audio import wav_seconds
from .datasets import DatasetService
from .models import ModelService
from .references import ReferenceService
from .remote import json_request
from .schemas import (
    DatasetCreateRequest,
    DatasetDeleteResponse,
    DatasetDetailRecord,
    DatasetListResponse,
    EventHistoryResponse,
    FineTuneConfigRequest,
    FineTuneDefaultsResponse,
    FineTuneStatusResponse,
    FineTuneStopRequest,
    FineTuneValidationResponse,
    JobListResponse,
    JobRecord,
    ModelActivateRequest,
    ModelStatusResponse,
    OpenAIAudioSpeechRequest,
    ReferenceListResponse,
    ReferenceRecord,
    RenderBenchmarkRequest,
    RenderCapabilitiesResponse,
    RenderSynthesisRequest,
    TranscriptUpdateRequest,
)
from .settings import load_settings

settings = load_settings()
settings.ensure_dirs()
events = EventService()
jobs = JobService(events, settings.logs_root / "jobs.jsonl", load_existing=True)
datasets = DatasetService(settings.training_root)
references = ReferenceService(
    settings.references_root,
    max_seconds=settings.reference_max_seconds,
    sample_rate=settings.reference_sample_rate,
    channels=settings.reference_channels,
)
models = ModelService(settings, events)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="Fish Speech Gateway API",
    description="Public gateway for Fish Speech render, references, models, preprocessing, and fine-tuning control.",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)
api = APIRouter(prefix="/api", tags=["api"])
v1 = APIRouter(prefix="/v1", tags=["v1"])


@app.exception_handler(ValueError)
async def value_error(_, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error(_, exc: RuntimeError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/healthz")
async def healthz():
    render, preprocess, finetune = await asyncio.gather(
        _probe_health(f"{settings.render_url}/healthz"),
        _probe_health(f"{settings.preprocess_url}/healthz"),
        _probe_health(f"{settings.finetune_url}/healthz"),
    )
    live = (
        await _probe_health(f"{settings.live_url}/healthz")
        if settings.live_enabled
        else {"status": "disabled", "ready": False, "engine": "disabled", "detail": "Live runtime is disabled."}
    )
    ready = bool(
        render.get("ready")
        and preprocess.get("status") == "ok"
        and finetune.get("status") == "ok"
        and (live.get("ready") if settings.live_enabled else True)
    )
    return {
        "status": "ok" if ready else "starting",
        "ready": ready,
        "services": {"render": render, "live": live, "preprocess": preprocess, "finetune": finetune},
    }


@api.get("/events")
async def event_stream():
    headers = {"Cache-Control": "no-store", "Connection": "keep-alive", "X-Accel-Buffering": "no"}
    return StreamingResponse(events.stream(), media_type="text/event-stream", headers=headers)


@api.get("/events/history", response_model=EventHistoryResponse)
async def event_history():
    return {"events": events.history()}


@api.get("/datasets", response_model=DatasetListResponse)
async def list_datasets():
    return {"datasets": datasets.list()}


@api.post("/datasets", response_model=DatasetDetailRecord)
async def create_dataset(payload: DatasetCreateRequest):
    data = datasets.create(payload.name)
    await events.publish("dataset.created", {"dataset": data})
    return data


@api.get("/datasets/{name}", response_model=DatasetDetailRecord)
async def get_dataset(name: str):
    return datasets.get(name)


@api.delete("/datasets/{name}", response_model=DatasetDeleteResponse)
async def delete_dataset(name: str):
    data = datasets.delete(name)
    await events.publish("dataset.deleted", {"dataset": data})
    return data


@api.post("/datasets/{name}/files", response_model=DatasetDetailRecord)
async def upload_files(name: str, files: list[UploadFile] = File(...), replace: bool = Form(False)):
    data = datasets.upload_files(name, files, replace)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.delete("/datasets/{name}/files/{filename}", response_model=DatasetDetailRecord)
async def delete_file(name: str, filename: str):
    data = datasets.delete_file(name, filename)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.post("/datasets/{name}/samples", response_model=DatasetDetailRecord)
async def save_sample(name: str, sample_name: str = Form(...), transcript_text: str = Form(""), replace: bool = Form(False), audio_file: UploadFile = File(...), lab_file: UploadFile | None = File(None)):
    data = datasets.save_sample(name, sample_name, audio_file, transcript_text, lab_file, replace)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.put("/datasets/{name}/samples/{sample}", response_model=DatasetDetailRecord)
async def save_transcript(name: str, sample: str, payload: TranscriptUpdateRequest):
    data = datasets.save_transcript(name, sample, payload.transcript)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.delete("/datasets/{name}/samples/{sample}", response_model=DatasetDetailRecord)
async def delete_sample(name: str, sample: str):
    data = datasets.delete_sample(name, sample)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.get("/references", response_model=ReferenceListResponse)
async def list_references():
    return {"references": references.list()}


@api.get("/references/{name}", response_model=ReferenceRecord)
async def get_reference(name: str):
    return references.get(name)


@api.get("/references/{name}/audio")
async def get_reference_audio(name: str):
    path = references.audio_path(name)
    return FileResponse(path, filename=path.name)


@api.post("/references", response_model=ReferenceRecord)
async def save_reference(name: str = Form(...), transcript: str = Form(...), replace: bool = Form(False), audio_file: UploadFile = File(...)):
    data = await asyncio.to_thread(references.save, name, audio_file, transcript, replace)
    await events.publish("reference.saved", {"reference": data})
    return data


@api.delete("/references/{name}")
async def delete_reference(name: str):
    data = references.delete(name)
    await events.publish("reference.deleted", data)
    return data


@api.get("/models", response_model=ModelStatusResponse)
async def model_status():
    return await models.status()


@api.post("/models/activate")
async def activate_model(payload: ModelActivateRequest):
    return await models.activate(payload.name, payload.target)


@api.post("/text/preprocess")
async def preprocess(payload: dict):
    return await json_request("POST", f"{settings.preprocess_url}/internal/preprocess", json=payload)


@api.get("/finetune", response_model=FineTuneDefaultsResponse)
async def finetune_defaults():
    return await json_request("GET", f"{settings.finetune_url}/internal/finetune")


@api.get("/finetune/status", response_model=FineTuneStatusResponse)
async def finetune_status():
    return await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")


@api.post("/finetune/validate", response_model=FineTuneValidationResponse)
async def finetune_validate(payload: FineTuneConfigRequest):
    return await json_request("POST", f"{settings.finetune_url}/internal/finetune/validate", json=_payload_from_model(payload))


@api.post("/finetune/start", response_model=JobRecord)
async def finetune_start(payload: FineTuneConfigRequest):
    data = await json_request("POST", f"{settings.finetune_url}/internal/finetune/start", json=_payload_from_model(payload))
    await events.publish("finetune.started", {"job": data})
    return data


@api.post("/finetune/stop", response_model=JobRecord)
async def finetune_stop(payload: FineTuneStopRequest | None = None):
    data = await json_request(
        "POST",
        f"{settings.finetune_url}/internal/finetune/stop",
        json=_payload_from_model(payload) if payload else {},
    )
    await events.publish("finetune.stopping", data)
    return data


@api.get("/jobs", response_model=JobListResponse)
async def list_jobs():
    rows = jobs.list()
    try:
        status = await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")
        if status.get("job"):
            rows = [status["job"], *rows]
    except Exception:
        pass
    return {"jobs": rows}


@api.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job(job_id: str):
    if job_id in jobs.rows:
        return jobs.get(job_id)
    status = await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")
    if status.get("job", {}).get("id") == job_id:
        return status["job"]
    raise ValueError(f"Job does not exist: {job_id}")


@api.post("/jobs/{job_id}/cancel", response_model=JobRecord)
async def cancel_job(job_id: str):
    if job_id in jobs.rows:
        return jobs.cancel(job_id)
    return await json_request("POST", f"{settings.finetune_url}/internal/finetune/stop", json={"job_id": job_id})


@api.get("/synthesis/capabilities", response_model=RenderCapabilitiesResponse)
async def synthesize_capabilities():
    return await _render_capabilities()


@api.post(
    "/synthesis",
    responses={200: {"content": {"audio/wav": {}}}},
)
async def synthesize(payload: RenderSynthesisRequest):
    return await _proxy_audio(_payload_from_model(payload), streaming=False)


@api.post(
    "/synthesis/stream",
    responses={200: {"content": {"audio/wav": {}}}},
)
async def synthesize_stream(payload: RenderSynthesisRequest):
    return await _proxy_audio(_payload_from_model(payload), streaming=True)


@api.get("/synthesis/stream/live")
async def synthesize_stream_live(text: str, reference_id: str | None = None):
    if not settings.live_enabled:
        raise HTTPException(status_code=409, detail="Live runtime is disabled.")
    job = jobs.create("synthesis", {"streaming": True, "reference_id": reference_id})
    jobs.update(job["id"], "running", {"streaming": True})
    await events.publish("synthesis.started", {"streaming": True, "reference_id": reference_id})
    client = httpx.AsyncClient(timeout=3600)
    request = client.build_request("GET", f"{settings.live_url}/internal/stream/live", params={"text": text, "reference_id": reference_id})
    response = await client.send(request, stream=True)
    if response.status_code >= 400:
        detail = (await response.aread()).decode("utf-8", errors="replace")
        await client.aclose()
        jobs.update(job["id"], "failed", error=detail)
        raise HTTPException(status_code=response.status_code, detail=detail)

    async def body():
        try:
            async for chunk in response.aiter_bytes():
                yield chunk
            jobs.update(job["id"], "completed", {"streaming": True})
        except Exception as exc:
            jobs.update(job["id"], "failed", error=str(exc))
            raise
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(body(), media_type="audio/wav", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@api.post("/synthesis/benchmark")
async def benchmark(payload: RenderBenchmarkRequest):
    data = _payload_from_model(payload)
    live = data.get("target", "render") == "live"
    if live and not settings.live_enabled:
        raise HTTPException(status_code=409, detail="Live runtime is disabled.")
    started = time.perf_counter()
    audio = await _fetch_audio(data, live=live)
    elapsed = time.perf_counter() - started
    seconds = wav_seconds(audio)
    runtime = await _probe_status(settings.live_url if live else settings.render_url)
    return {
        "target": "live" if live else "render",
        "engine": runtime.get("engine", "s2cpp" if live and settings.live_engine == "s2cpp" else "fish"),
        "model_path": runtime.get("active_model_path", str(settings.live_model_path if live else settings.model_path)),
        "elapsed_sec": round(elapsed, 3),
        "audio_sec": round(seconds, 3),
        "rtf": round(elapsed / seconds, 3) if seconds else None,
        "bytes": len(audio),
    }


async def _proxy_audio(payload: dict, streaming: bool):
    job = jobs.create("synthesis", {"streaming": streaming, "reference_id": payload.get("reference_id")})
    jobs.update(job["id"], "running", {"streaming": streaming})
    await events.publish("synthesis.started", {"streaming": streaming, "reference_id": payload.get("reference_id")})
    try:
        audio = await _fetch_audio(payload, live=False)
        jobs.update(job["id"], "completed", {"streaming": streaming})
        return Response(content=audio, media_type="audio/wav")
    except HTTPException as exc:
        jobs.update(job["id"], "failed", error=str(exc.detail))
        raise
    except Exception as exc:
        jobs.update(job["id"], "failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


async def _fetch_audio(payload: dict, live: bool) -> bytes:
    if live and not settings.live_enabled:
        raise HTTPException(status_code=409, detail="Live runtime is disabled.")
    prepared_payload = dict(payload)
    if not live and payload.get("reference_id"):
        try:
            await asyncio.to_thread(references.ensure_runtime_ready, str(payload.get("reference_id")))
            if not prepared_payload.get("references"):
                prepared_payload["references"] = [
                    await asyncio.to_thread(references.render_payload, str(payload.get("reference_id")))
                ]
            # Use explicit reference payloads for render runtime to keep target text
            # separate from saved reference transcript all the way to Fish Speech.
            prepared_payload["reference_id"] = None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    url = f"{settings.live_url if live else settings.render_url}/internal/synthesize"
    async with httpx.AsyncClient(timeout=3600) as client:
        response = await client.post(url, json=prepared_payload)
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail or "Synthesis failed")
    return response.content


async def _probe_health(url: str) -> dict:
    try:
        return await json_request("GET", url, timeout=30)
    except Exception as exc:
        return {"status": "down", "ready": False, "detail": str(exc)}


async def _probe_status(base_url: str) -> dict:
    try:
        return await json_request("GET", f"{base_url}/internal/status", timeout=30)
    except Exception:
        return {}


@v1.get("/health")
async def v1_health():
    return await healthz()


@v1.get("/events")
async def v1_events():
    return await event_stream()


@v1.get("/events/history", response_model=EventHistoryResponse)
async def v1_event_history():
    return await event_history()


@v1.get("/datasets", response_model=DatasetListResponse)
async def v1_list_datasets():
    return await list_datasets()


@v1.post("/datasets", response_model=DatasetDetailRecord)
async def v1_create_dataset(payload: DatasetCreateRequest):
    return await create_dataset(payload)


@v1.get("/datasets/{name}", response_model=DatasetDetailRecord)
async def v1_get_dataset(name: str):
    return await get_dataset(name)


@v1.delete("/datasets/{name}", response_model=DatasetDeleteResponse)
async def v1_delete_dataset(name: str):
    return await delete_dataset(name)


@v1.post("/datasets/{name}/files", response_model=DatasetDetailRecord)
async def v1_upload_files(name: str, files: list[UploadFile] = File(...), replace: bool = Form(False)):
    return await upload_files(name=name, files=files, replace=replace)


@v1.delete("/datasets/{name}/files/{filename}", response_model=DatasetDetailRecord)
async def v1_delete_file(name: str, filename: str):
    return await delete_file(name=name, filename=filename)


@v1.post("/datasets/{name}/samples", response_model=DatasetDetailRecord)
async def v1_save_sample(
    name: str,
    sample_name: str = Form(...),
    transcript_text: str = Form(""),
    replace: bool = Form(False),
    audio_file: UploadFile = File(...),
    lab_file: UploadFile | None = File(None),
):
    return await save_sample(
        name=name,
        sample_name=sample_name,
        transcript_text=transcript_text,
        replace=replace,
        audio_file=audio_file,
        lab_file=lab_file,
    )


@v1.put("/datasets/{name}/samples/{sample}", response_model=DatasetDetailRecord)
async def v1_save_transcript(name: str, sample: str, payload: TranscriptUpdateRequest):
    return await save_transcript(name=name, sample=sample, payload=payload)


@v1.delete("/datasets/{name}/samples/{sample}", response_model=DatasetDetailRecord)
async def v1_delete_sample(name: str, sample: str):
    return await delete_sample(name=name, sample=sample)


@v1.get("/render/health")
async def v1_render_health():
    return await _probe_health(f"{settings.render_url}/healthz")


@v1.get("/render/status", response_model=ModelStatusResponse)
async def v1_render_status():
    return await models.status()


@v1.get("/render/capabilities", response_model=RenderCapabilitiesResponse)
async def v1_render_capabilities():
    return await _render_capabilities()


@v1.get("/render/references", response_model=ReferenceListResponse)
async def v1_list_references():
    return {"references": references.list()}


@v1.get("/render/references/{name}", response_model=ReferenceRecord)
async def v1_get_reference(name: str):
    return references.get(name)


@v1.get("/render/references/{name}/audio")
async def v1_get_reference_audio(name: str):
    return await get_reference_audio(name)


@v1.post("/render/references", response_model=ReferenceRecord)
async def v1_save_reference(
    name: str = Form(...),
    transcript: str = Form(...),
    replace: bool = Form(False),
    audio_file: UploadFile = File(...),
):
    return await save_reference(name=name, transcript=transcript, replace=replace, audio_file=audio_file)


@v1.delete("/render/references/{name}")
async def v1_delete_reference(name: str):
    return await delete_reference(name)


@v1.get("/render/models", response_model=ModelStatusResponse)
async def v1_model_status():
    return await model_status()


@v1.post("/render/models/activate")
async def v1_activate_model(payload: ModelActivateRequest):
    return await activate_model(payload)


@v1.post("/render/preprocess")
async def v1_preprocess(payload: dict):
    return await preprocess(payload)


@v1.post(
    "/render/speech",
    responses={200: {"content": {"audio/wav": {}}}},
)
async def v1_render_speech(payload: RenderSynthesisRequest):
    return await _proxy_audio(_payload_from_model(payload), streaming=False)


@v1.post("/render/benchmark")
async def v1_render_benchmark(payload: RenderBenchmarkRequest):
    return await benchmark(payload)


@v1.get("/finetune", response_model=FineTuneDefaultsResponse)
async def v1_finetune_defaults():
    return await finetune_defaults()


@v1.get("/finetune/status", response_model=FineTuneStatusResponse)
async def v1_finetune_status():
    return await finetune_status()


@v1.post("/finetune/validate", response_model=FineTuneValidationResponse)
async def v1_finetune_validate(payload: FineTuneConfigRequest):
    return await finetune_validate(payload)


@v1.post("/finetune/start", response_model=JobRecord)
async def v1_finetune_start(payload: FineTuneConfigRequest):
    return await finetune_start(payload)


@v1.post("/finetune/stop", response_model=JobRecord)
async def v1_finetune_stop(payload: FineTuneStopRequest | None = None):
    return await finetune_stop(payload)


@v1.get("/jobs", response_model=JobListResponse)
async def v1_list_jobs():
    return await list_jobs()


@v1.get("/jobs/{job_id}", response_model=JobRecord)
async def v1_get_job(job_id: str):
    return await get_job(job_id)


@v1.post("/jobs/{job_id}/cancel", response_model=JobRecord)
async def v1_cancel_job(job_id: str):
    return await cancel_job(job_id)


@v1.post(
    "/audio/speech",
    responses={200: {"content": {"audio/wav": {}}}},
)
async def v1_audio_speech(payload: OpenAIAudioSpeechRequest):
    runtime_payload = await _payload_from_openai_request(payload)
    return await _proxy_audio(runtime_payload, streaming=False)


def _payload_from_model(payload) -> dict:
    data = payload.model_dump(exclude_none=True)
    extra = getattr(payload, "model_extra", None) or {}
    data.update({key: value for key, value in extra.items() if value is not None})
    return data


async def _payload_from_openai_request(payload: OpenAIAudioSpeechRequest) -> dict:
    if payload.response_format != "wav":
        raise HTTPException(status_code=400, detail="Only response_format='wav' is supported.")
    if payload.speed is not None and abs(float(payload.speed) - 1.0) > 1e-6:
        raise HTTPException(status_code=400, detail="Fish render does not support speed adjustment per request.")
    await _ensure_requested_render_model(payload.model)
    extra = getattr(payload, "model_extra", None) or {}
    runtime_payload = {
        "text": payload.input,
        "reference_id": payload.reference_id or payload.voice,
        "references": payload.references,
        "chunk_length": payload.chunk_length,
        "top_p": payload.top_p,
        "repetition_penalty": payload.repetition_penalty,
        "temperature": payload.temperature,
        "seed": payload.seed,
        "normalize": payload.normalize,
        "use_memory_cache": payload.use_memory_cache,
    }
    runtime_payload.update(
        {
            key: value
            for key, value in extra.items()
            if value is not None and key not in {"input", "model", "voice", "reference_id", "response_format", "speed"}
        }
    )
    return {key: value for key, value in runtime_payload.items() if value is not None}


async def _ensure_requested_render_model(name: str | None) -> None:
    requested = str(name or "").strip()
    if not requested:
        return
    status = await models.status()
    active = status.get("render")
    if active and active.get("name") == requested:
        return
    known = next((item for item in status.get("models", []) if item.get("name") == requested and item.get("engine") == "fish"), None)
    if known:
        raise HTTPException(
            status_code=409,
            detail=f"Requested render model '{requested}' is not active. Activate it first via /api/models/activate or /v1/render/models/activate.",
        )
    raise HTTPException(status_code=400, detail=f"Unknown render model: {requested}")


async def _render_capabilities() -> dict:
    runtime = await _probe_status(settings.render_url)
    active_model_name = None
    try:
        model_status = await models.status()
        active = model_status.get("render")
        active_model_name = active.get("name") if active else None
    except Exception:
        pass

    return {
        "engine": "fish",
        "ready": bool(runtime.get("ready")),
        "active_model_path": runtime.get("active_model_path", str(settings.model_path)),
        "active_model_name": active_model_name,
        "device": runtime.get("device"),
        "dtype": runtime.get("dtype"),
        "compile_enabled": runtime.get("compile_enabled"),
        "supports_reference_id": True,
        "supports_explicit_references": True,
        "supported_output_formats": ["wav"],
        "supported_request_fields": [
            "text",
            "reference_id",
            "references",
            "chunk_length",
            "top_p",
            "repetition_penalty",
            "temperature",
            "seed",
            "normalize",
            "use_memory_cache",
        ],
        "defaults": {
            "chunk_length": int(settings_env("CHUNK_LENGTH", "240")),
            "temperature": float(settings_env("TEMPERATURE", "0.62")),
            "top_p": float(settings_env("TOP_P", "0.88")),
            "repetition_penalty": float(settings_env("REPETITION_PENALTY", "1.15")),
            "seed": int(settings_env("SEED")) if settings_env("SEED") else None,
            "normalize": settings_env("NORMALIZE_TEXT", "true").lower() == "true",
            "use_memory_cache": settings_env("USE_MEMORY_CACHE", "on"),
        },
        "limits": {
            "max_text_length": int(settings_env("MAX_TEXT_LENGTH", "1500")),
            "reference_max_seconds": settings.reference_max_seconds,
            "reference_sample_rate": settings.reference_sample_rate,
            "reference_channels": settings.reference_channels,
        },
        "detail": runtime.get("detail", ""),
    }


def settings_env(name: str, default: str | None = None) -> str | None:
    import os

    return os.getenv(name, default)


app.include_router(api)
app.include_router(v1)
