from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.events import EventService
from shared.jobs import JobService

from .datasets import DatasetService
from .finetune import FineTuneService
from .queue import QueueService
from .settings import load_settings

settings = load_settings()
settings.ensure_dirs()
events = EventService()
jobs = JobService(events, settings.logs_root / "finetune-jobs.jsonl", load_existing=True)
queue = QueueService(jobs)
datasets = DatasetService(settings.training_root)
finetune = FineTuneService(settings, events, jobs, queue)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await queue.startup()
    yield
    await queue.shutdown()


app = FastAPI(title="finetune-api", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/internal/finetune")
async def defaults():
    return {"defaults": finetune.defaults(), "presets": {"lora_configs": ["r_4_alpha_8", "r_8_alpha_16", "r_16_alpha_32", "r_32_alpha_64"]}, "datasets": datasets.list()}


@app.get("/internal/finetune/status")
async def status():
    return finetune.status()


@app.post("/internal/finetune/validate")
async def validate(payload: dict):
    return finetune.validate(payload)


@app.post("/internal/finetune/start")
async def start(payload: dict):
    return finetune.start(payload)


@app.post("/internal/finetune/stop")
async def stop(payload: dict | None = None):
    return finetune.stop(payload.get("job_id") if payload else None)
