import asyncio
from contextlib import asynccontextmanager
import time

import httpx
from fastapi import FastAPI, APIRouter, File, Form, UploadFile, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse

from shared.events import EventService
from shared.jobs import JobService

from .audio import wav_seconds
from .datasets import DatasetService
from .models import ModelService
from .references import ReferenceService
from .remote import json_request
from .settings import load_settings

settings = load_settings()
settings.ensure_dirs()
events = EventService()
jobs = JobService(events, settings.logs_root / "jobs.jsonl", load_existing=True)
datasets = DatasetService(settings.training_root)
references = ReferenceService(settings.references_root)
models = ModelService(settings, events)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(title="api-gateway", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
api = APIRouter(prefix="/api")


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


@api.get("/events/history")
async def event_history():
    return {"events": events.history()}


@api.get("/datasets")
async def list_datasets():
    return {"datasets": datasets.list()}


@api.post("/datasets")
async def create_dataset(payload: dict):
    data = datasets.create(payload.get("name", ""))
    await events.publish("dataset.created", {"dataset": data})
    return data


@api.get("/datasets/{name}")
async def get_dataset(name: str):
    return datasets.get(name)


@api.delete("/datasets/{name}")
async def delete_dataset(name: str):
    data = datasets.delete(name)
    await events.publish("dataset.deleted", {"dataset": data})
    return data


@api.post("/datasets/{name}/files")
async def upload_files(name: str, files: list[UploadFile] = File(...), replace: bool = Form(False)):
    data = datasets.upload_files(name, files, replace)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.delete("/datasets/{name}/files/{filename}")
async def delete_file(name: str, filename: str):
    data = datasets.delete_file(name, filename)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.post("/datasets/{name}/samples")
async def save_sample(name: str, sample_name: str = Form(...), transcript_text: str = Form(""), replace: bool = Form(False), audio_file: UploadFile = File(...), lab_file: UploadFile | None = File(None)):
    data = datasets.save_sample(name, sample_name, audio_file, transcript_text, lab_file, replace)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.put("/datasets/{name}/samples/{sample}")
async def save_transcript(name: str, sample: str, payload: dict):
    data = datasets.save_transcript(name, sample, payload.get("transcript", ""))
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.delete("/datasets/{name}/samples/{sample}")
async def delete_sample(name: str, sample: str):
    data = datasets.delete_sample(name, sample)
    await events.publish("dataset.updated", {"dataset": data})
    return data


@api.get("/references")
async def list_references():
    return {"references": references.list()}


@api.get("/references/{name}")
async def get_reference(name: str):
    return references.get(name)


@api.post("/references")
async def save_reference(name: str = Form(...), transcript: str = Form(...), replace: bool = Form(False), audio_file: UploadFile = File(...)):
    data = references.save(name, audio_file, transcript, replace)
    await events.publish("reference.saved", {"reference": data})
    return data


@api.delete("/references/{name}")
async def delete_reference(name: str):
    data = references.delete(name)
    await events.publish("reference.deleted", data)
    return data


@api.get("/models")
async def model_status():
    return await models.status()


@api.post("/models/activate")
async def activate_model(payload: dict):
    return await models.activate(payload.get("name", ""), payload.get("target", "render"))


@api.post("/text/preprocess")
async def preprocess(payload: dict):
    return await json_request("POST", f"{settings.preprocess_url}/internal/preprocess", json=payload)


@api.get("/finetune")
async def finetune_defaults():
    return await json_request("GET", f"{settings.finetune_url}/internal/finetune")


@api.get("/finetune/status")
async def finetune_status():
    return await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")


@api.post("/finetune/validate")
async def finetune_validate(payload: dict):
    return await json_request("POST", f"{settings.finetune_url}/internal/finetune/validate", json=payload)


@api.post("/finetune/start")
async def finetune_start(payload: dict):
    data = await json_request("POST", f"{settings.finetune_url}/internal/finetune/start", json=payload)
    await events.publish("finetune.started", {"job": data})
    return data


@api.post("/finetune/stop")
async def finetune_stop(payload: dict | None = None):
    data = await json_request("POST", f"{settings.finetune_url}/internal/finetune/stop", json=payload or {})
    await events.publish("finetune.stopping", data)
    return data


@api.get("/jobs")
async def list_jobs():
    rows = jobs.list()
    try:
        status = await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")
        if status.get("job"):
            rows = [status["job"], *rows]
    except Exception:
        pass
    return {"jobs": rows}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id in jobs.rows:
        return jobs.get(job_id)
    status = await json_request("GET", f"{settings.finetune_url}/internal/finetune/status")
    if status.get("job", {}).get("id") == job_id:
        return status["job"]
    raise ValueError(f"Job does not exist: {job_id}")


@api.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    if job_id in jobs.rows:
        return jobs.cancel(job_id)
    return await json_request("POST", f"{settings.finetune_url}/internal/finetune/stop", json={"job_id": job_id})


@api.post("/synthesis")
async def synthesize(payload: dict):
    return await _proxy_audio(payload, streaming=False)


@api.post("/synthesis/stream")
async def synthesize_stream(payload: dict):
    return await _proxy_audio(payload, streaming=True)


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
async def benchmark(payload: dict):
    live = payload.get("target", "render") == "live"
    if live and not settings.live_enabled:
        raise HTTPException(status_code=409, detail="Live runtime is disabled.")
    started = time.perf_counter()
    audio = await _fetch_audio(payload, live=live)
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
    url = f"{settings.live_url if live else settings.render_url}/internal/synthesize"
    async with httpx.AsyncClient(timeout=3600) as client:
        response = await client.post(url, json=payload)
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


app.include_router(api)
