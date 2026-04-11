import asyncio
from dataclasses import replace
import logging
from pathlib import Path
import time
from typing import Any

import torch

from fish_speech.inference_engine import TTSInferenceEngine
from fish_speech.models.dac.inference import load_model as load_decoder_model
from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
from fish_speech.utils.schema import ServeTTSRequest

from .audio import audio_array_to_wav, wav_seconds
from .settings import load_settings

logger = logging.getLogger(__name__)


class FishRuntime:
    def __init__(self):
        self.settings = load_settings()
        self.engine: TTSInferenceEngine | None = None
        self._llama_queue: Any | None = None
        self._device = self._resolve_device(self.settings.device)
        self._precision = self._resolve_precision(self.settings.dtype, self._device)
        self._compile_enabled = bool(self.settings.enable_compile and self._device.startswith("cuda"))
        self._lock = asyncio.Lock()
        self._ready = False
        self._error = ""

    async def startup(self):
        async with self._lock:
            self._error = ""
            try:
                await self._load_engine(self.settings.model_path)
            except Exception as exc:
                self._error = str(exc)
                logger.exception("Render runtime startup failed")

    async def switch_model(self, model_path: str) -> dict:
        async with self._lock:
            target = str(model_path or "").strip()
            if not target:
                raise ValueError("Model path is required.")

            previous = self.settings.model_path
            self._error = ""
            try:
                await self._load_engine(target)
            except Exception as exc:
                self._error = str(exc)
                logger.exception("Render model switch failed")
                if str(previous) != target and previous.exists():
                    try:
                        await self._load_engine(previous)
                        self._error = ""
                    except Exception as restore_exc:
                        self._error = str(restore_exc)
                raise RuntimeError(self._error) from exc

        return self.status()

    async def _load_engine(self, model_path: str | Path) -> None:
        target = Path(model_path)
        self._validate_model_dir(target)

        runtime_device = self._resolve_device(self.settings.device)
        runtime_precision = self._resolve_precision(self.settings.dtype, runtime_device)
        compile_enabled = bool(self.settings.enable_compile and runtime_device.startswith("cuda"))

        logger.info(
            "Loading Fish Speech render runtime | model=%s | device=%s | dtype=%s | compile=%s",
            target,
            runtime_device,
            getattr(runtime_precision, "name", str(runtime_precision)).replace("torch.", ""),
            compile_enabled,
        )

        self._ready = False
        self._teardown_engine()

        decoder_checkpoint = target / "codec.pth"
        llama_queue = launch_thread_safe_queue(
            checkpoint_path=str(target),
            device=runtime_device,
            precision=runtime_precision,
            compile=compile_enabled,
        )
        decoder_model = load_decoder_model(
            config_name="modded_dac_vq",
            checkpoint_path=str(decoder_checkpoint),
            device=runtime_device,
        )

        self.engine = TTSInferenceEngine(
            llama_queue=llama_queue,
            decoder_model=decoder_model,
            precision=runtime_precision,
            compile=compile_enabled,
        )
        self._llama_queue = llama_queue
        self._device = runtime_device
        self._precision = runtime_precision
        self._compile_enabled = compile_enabled
        self.settings = replace(self.settings, model_path=target)

        await asyncio.to_thread(self._warmup)
        self._ready = True
        logger.info("Fish Speech render runtime ready")

    def _warmup(self):
        if not self.engine:
            raise RuntimeError("Render runtime was not initialized")

        logger.info("Warm-up render runtime")
        dummy_req = ServeTTSRequest(
            text=(
                "Загружайте датасеты, обучайте голосовые профили, активируйте модели "
                "и запускайте синтез речи в quality-first режиме без лишних задержек."
            ),
            format="wav",
            streaming=False,
            normalize=self.settings.normalize,
            chunk_length=self.settings.chunk_length,
            use_memory_cache=self.settings.use_memory_cache,
        )
        for result in self.engine.inference(dummy_req):
            if result.code == "error":
                raise result.error or RuntimeError("Warm-up failed")
        logger.info("Warm-up completed")

    async def shutdown(self):
        self._ready = False
        self._teardown_engine()

    def status(self) -> dict:
        return {
            "active_model_path": str(self.settings.model_path),
            "ready": self._ready,
            "engine": "fish",
            "compile_enabled": self._compile_enabled,
            "dtype": getattr(self._precision, "name", str(self._precision)).replace("torch.", ""),
            "device": self._device,
            "detail": self._error,
        }

    def synthesize(self, payload: dict) -> bytes:
        if not self._ready or not self.engine:
            raise RuntimeError("Inference engine is not ready")

        text = str(payload.get("text", ""))
        if not text.strip():
            raise ValueError("Text must not be empty")
        if self.settings.max_text_length > 0 and len(text) > self.settings.max_text_length:
            raise ValueError(f"Text is too long for render runtime: {len(text)} > {self.settings.max_text_length}")

        start_time = time.perf_counter()
        req = ServeTTSRequest(
            text=text,
            reference_id=payload.get("reference_id"),
            references=payload.get("references") or [],
            format="wav",
            streaming=False,
            chunk_length=int(self._payload_value(payload, "chunk_length", self.settings.chunk_length)),
            top_p=float(self._payload_value(payload, "top_p", self.settings.top_p)),
            repetition_penalty=float(
                self._payload_value(payload, "repetition_penalty", self.settings.repetition_penalty)
            ),
            temperature=float(self._payload_value(payload, "temperature", self.settings.temperature)),
            seed=self._payload_value(payload, "seed", self.settings.seed),
            normalize=bool(self._payload_value(payload, "normalize", self.settings.normalize)),
            use_memory_cache=str(self._payload_value(payload, "use_memory_cache", self.settings.use_memory_cache)),
        )

        sample_rate = 44_100
        audio = None
        for result in self.engine.inference(req):
            if result.code == "error":
                raise RuntimeError(str(result.error or "Inference error"))
            if result.code == "final" and result.audio:
                sample_rate, audio = result.audio

        if audio is None:
            raise RuntimeError("No audio generated")

        audio_bytes = audio_array_to_wav(audio, sample_rate)
        elapsed = time.perf_counter() - start_time
        duration = wav_seconds(audio_bytes)
        rtf = elapsed / duration if duration > 0 else 0.0

        logger.info(
            "Render synthesized %s chars -> %.2fs audio in %.2fs -> RTF=%.3f",
            len(req.text),
            duration,
            elapsed,
            rtf,
        )
        return audio_bytes

    def _teardown_engine(self) -> None:
        if self._llama_queue is not None:
            try:
                self._llama_queue.put(None)
            except Exception:
                logger.debug("Failed to stop llama queue cleanly", exc_info=True)
            self._llama_queue = None

        if self.engine is not None:
            del self.engine
            self.engine = None

        if self._device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _resolve_device(self, requested: str) -> str:
        requested = (requested or "cuda").strip().lower()
        if requested.startswith("cuda"):
            if torch.cuda.is_available():
                return requested
            if torch.backends.mps.is_available():
                return "mps"
            return "cpu"
        if requested == "mps" and torch.backends.mps.is_available():
            return "mps"
        if requested == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _resolve_precision(self, requested: str, device: str):
        normalized = (requested or "bfloat16").strip().lower()
        mapping = {
            "float16": torch.float16,
            "half": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
            "full": torch.float32,
        }
        precision = mapping.get(normalized)
        if precision is None:
            raise ValueError(f"Unsupported dtype: {requested}")
        if device in {"cpu", "mps"} and precision is torch.bfloat16:
            return torch.float32
        return precision

    def _validate_model_dir(self, model_dir: Path) -> None:
        if not model_dir.exists():
            raise FileNotFoundError(f"Render model path does not exist: {model_dir}")
        if not model_dir.is_dir():
            raise ValueError(f"Render model path must be a directory: {model_dir}")
        codec_path = model_dir / "codec.pth"
        if not codec_path.exists():
            raise FileNotFoundError(f"Render model is missing codec checkpoint: {codec_path}")

    @staticmethod
    def _payload_value(payload: dict, key: str, default):
        value = payload.get(key)
        return default if value is None else value
