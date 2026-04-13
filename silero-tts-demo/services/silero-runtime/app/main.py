from __future__ import annotations

import io
import logging
import os
import re
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field


logger = logging.getLogger("silero-runtime")

SUPPORTED_SPEAKERS = ("aidar", "baya", "kseniya", "xenia", "eugene")
SUPPORTED_SAMPLE_RATES = (8000, 24000, 48000)


@dataclass(frozen=True)
class Settings:
    model_url: str
    model_path: Path
    device_preference: str
    threads: int
    model_id: str
    language: str
    default_speaker: str
    default_sample_rate: int
    max_text_chars: int
    chunk_chars: int
    sentence_pause_ms: int


class SynthesisRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=20000)
    speaker: str | None = None
    sample_rate: int | None = None
    put_accent: bool = True
    put_yo: bool = True
    use_ssml: bool = False


class RuntimeState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.lock = threading.Lock()
        self.model = None
        self.device = "cpu"


def load_settings() -> Settings:
    data_root = Path("/app/data")
    return Settings(
        model_url=os.getenv("SILERO_MODEL_URL", "https://models.silero.ai/models/tts/ru/v5_ru.pt"),
        model_path=data_root / "models" / "v5_ru.pt",
        device_preference=os.getenv("SILERO_DEVICE", "cuda"),
        threads=max(1, int(os.getenv("SILERO_THREADS", "4"))),
        model_id=os.getenv("SILERO_MODEL_ID", "v5_ru"),
        language=os.getenv("SILERO_LANGUAGE", "ru"),
        default_speaker=os.getenv("SILERO_DEFAULT_SPEAKER", "xenia"),
        default_sample_rate=int(os.getenv("SILERO_DEFAULT_SAMPLE_RATE", "48000")),
        max_text_chars=int(os.getenv("SILERO_MAX_TEXT_CHARS", "6000")),
        chunk_chars=int(os.getenv("SILERO_CHUNK_CHARS", "350")),
        sentence_pause_ms=int(os.getenv("SILERO_SENTENCE_PAUSE_MS", "160")),
    )


def resolve_device(preferred: str) -> torch.device:
    preferred = (preferred or "cpu").strip().lower()
    if preferred.startswith("cuda"):
        if torch.cuda.is_available():
            return torch.device(preferred)
        logger.warning("cuda was requested, but no GPU is available; falling back to cpu")
    return torch.device("cpu")


def ensure_model_file(settings: Settings) -> None:
    settings.model_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.model_path.exists():
        logger.info("using cached model file: %s", settings.model_path)
        return
    logger.info("downloading official model from %s", settings.model_url)
    torch.hub.download_url_to_file(settings.model_url, str(settings.model_path))
    logger.info("model file downloaded to %s", settings.model_path)


def load_model(state: RuntimeState) -> None:
    settings = state.settings
    logger.info("preparing Silero TTS model %s", settings.model_id)
    ensure_model_file(settings)
    torch.set_num_threads(settings.threads)
    device = resolve_device(settings.device_preference)
    logger.info("loading model on device %s", device)
    model = torch.package.PackageImporter(str(settings.model_path)).load_pickle("tts_models", "model")
    model.to(device)
    state.model = model
    state.device = str(device)
    logger.info("Silero runtime is ready")


def normalize_plain_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_long_text(text: str, chunk_chars: int) -> list[str]:
    text = normalize_plain_text(text)
    if len(text) <= chunk_chars:
        return [text]

    raw_sentences = [item.strip() for item in re.split(r"(?<=[.!?…])\s+", text) if item.strip()]
    chunks: list[str] = []
    current = ""

    for sentence in raw_sentences:
        if len(sentence) <= chunk_chars:
            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= chunk_chars:
                current = candidate
            else:
                chunks.append(current)
                current = sentence
            continue

        if current:
            chunks.append(current)
            current = ""

        words = sentence.split()
        piece = ""
        for word in words:
            candidate = word if not piece else f"{piece} {word}"
            if len(candidate) <= chunk_chars:
                piece = candidate
                continue
            if piece:
                chunks.append(piece)
            if len(word) <= chunk_chars:
                piece = word
                continue
            for start in range(0, len(word), chunk_chars):
                chunks.append(word[start : start + chunk_chars])
            piece = ""
        if piece:
            chunks.append(piece)

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk]


def to_numpy_audio(audio) -> np.ndarray:
    if isinstance(audio, torch.Tensor):
        waveform = audio.detach().cpu().numpy()
    else:
        waveform = np.asarray(audio)
    waveform = waveform.astype(np.float32).reshape(-1)
    return waveform


def synthesize_audio(state: RuntimeState, payload: SynthesisRequest) -> tuple[bytes, dict]:
    settings = state.settings
    if state.model is None:
        raise RuntimeError("Silero model is not loaded yet.")

    speaker = (payload.speaker or settings.default_speaker).strip().lower()
    if speaker not in SUPPORTED_SPEAKERS:
        raise ValueError(f"speaker must be one of: {', '.join(SUPPORTED_SPEAKERS)}")

    sample_rate = int(payload.sample_rate or settings.default_sample_rate)
    if sample_rate not in SUPPORTED_SAMPLE_RATES:
        raise ValueError(f"sample_rate must be one of: {', '.join(map(str, SUPPORTED_SAMPLE_RATES))}")

    source_text = payload.text.strip()
    if not source_text:
        raise ValueError("text is required")
    if len(source_text) > settings.max_text_chars:
        raise ValueError(f"text is too long; limit is {settings.max_text_chars} characters")

    if payload.use_ssml:
        segments = [source_text]
    else:
        segments = split_long_text(source_text, settings.chunk_chars)

    pause = np.zeros(int(sample_rate * settings.sentence_pause_ms / 1000.0), dtype=np.float32)
    rendered_segments: list[np.ndarray] = []

    with state.lock:
        for segment in segments:
            if payload.use_ssml:
                audio = state.model.apply_tts(
                    ssml_text=segment,
                    speaker=speaker,
                    sample_rate=sample_rate,
                )
            else:
                audio = state.model.apply_tts(
                    text=segment,
                    speaker=speaker,
                    sample_rate=sample_rate,
                    put_accent=payload.put_accent,
                    put_yo=payload.put_yo,
                )
            rendered_segments.append(to_numpy_audio(audio))

    stitched: list[np.ndarray] = []
    for index, segment_audio in enumerate(rendered_segments):
        stitched.append(segment_audio)
        if index < len(rendered_segments) - 1 and pause.size:
            stitched.append(pause)

    waveform = np.concatenate(stitched) if stitched else np.zeros(1, dtype=np.float32)
    buffer = io.BytesIO()
    sf.write(buffer, waveform, sample_rate, format="WAV", subtype="PCM_16")

    meta = {
        "speaker": speaker,
        "sample_rate": sample_rate,
        "segments": len(segments),
        "duration_sec": round(float(len(waveform) / sample_rate), 3),
        "device": state.device,
        "use_ssml": payload.use_ssml,
    }
    return buffer.getvalue(), meta


def example_payloads() -> list[dict]:
    return [
        {
            "id": "welcome",
            "title": "Базовый русский синтез",
            "speaker": "xenia",
            "sample_rate": 48000,
            "put_accent": True,
            "put_yo": True,
            "use_ssml": False,
            "text": "Здравствуйте! Это демонстрация русского синтеза речи на Silero TTS.",
        },
        {
            "id": "stress",
            "title": "Ударения и ё",
            "speaker": "baya",
            "sample_rate": 48000,
            "put_accent": True,
            "put_yo": True,
            "use_ssml": False,
            "text": "Все ёлки зелёные, а зам+ок на двери закрыт. Мука и мук+а звучат по-разному.",
        },
        {
            "id": "ssml",
            "title": "SSML пауза",
            "speaker": "kseniya",
            "sample_rate": 48000,
            "put_accent": True,
            "put_yo": True,
            "use_ssml": True,
            "text": "<speak>Здравствуйте!<break time=\"500ms\"/>Это демонстрация паузы внутри синтеза речи.</speak>",
        },
    ]


settings = load_settings()
runtime = RuntimeState(settings)


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_model(runtime)
    yield


app = FastAPI(title="silero-runtime", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(ValueError)
async def handle_value_error(_, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RuntimeError)
async def handle_runtime_error(_, exc: RuntimeError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok" if runtime.model is not None else "starting",
        "ready": runtime.model is not None,
        "model_id": settings.model_id,
        "language": settings.language,
        "device": runtime.device,
    }


@app.get("/api/status")
async def status():
    return {
        "status": "ok" if runtime.model is not None else "starting",
        "ready": runtime.model is not None,
        "model_id": settings.model_id,
        "language": settings.language,
        "device": runtime.device,
        "default_speaker": settings.default_speaker,
        "default_sample_rate": settings.default_sample_rate,
        "speakers": list(SUPPORTED_SPEAKERS),
        "sample_rates": list(SUPPORTED_SAMPLE_RATES),
        "examples": example_payloads(),
        "notes": [
            "Русская модель v5_ru использует официальные голоса Silero.",
            "Для длинного обычного текста runtime автоматически делит его по предложениям.",
            "В SSML-режиме используйте теги <speak> и <break time=\"...\"/>.",
        ],
    }


@app.get("/api/events")
async def noop_events():
    return Response(status_code=204)


@app.post("/api/synthesize")
async def synthesize(payload: SynthesisRequest):
    try:
        audio_bytes, meta = synthesize_audio(runtime, payload)
    except ValueError:
        raise
    except RuntimeError:
        raise
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.exception("Silero synthesis failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-store",
            "X-Silero-Speaker": str(meta["speaker"]),
            "X-Silero-Sample-Rate": str(meta["sample_rate"]),
            "X-Silero-Segments": str(meta["segments"]),
            "X-Silero-Duration-Sec": str(meta["duration_sec"]),
        },
    )
