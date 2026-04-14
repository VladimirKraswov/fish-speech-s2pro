import asyncio
import base64
import gc
from dataclasses import replace
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import threading
import time
from typing import Any, Protocol

import httpx
import torch

from fish_speech.inference_engine import TTSInferenceEngine
from fish_speech.models.dac.inference import load_model as load_decoder_model
from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
from fish_speech.utils.schema import ServeTTSRequest

from .audio import audio_array_to_wav, concatenate_audio_segments, wav_seconds
from .settings import Settings, load_settings

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac"}
AUDIO_MIME_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}


class RenderRuntime(Protocol):
    async def startup(self): ...

    async def shutdown(self): ...

    async def switch_model(self, model_path: str) -> dict: ...

    def status(self) -> dict: ...

    def synthesize(self, payload: dict) -> bytes: ...


class FishRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
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
        self._configure_compile_runtime(compile_enabled)

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
                "chunk_length": self.settings.chunk_length,
                "temperature": self.settings.temperature,
                "top_p": self.settings.top_p,
                "repetition_penalty": self.settings.repetition_penalty,
                "seed": self.settings.seed,
                "normalize": self.settings.normalize,
                "use_memory_cache": self.settings.use_memory_cache,
            },
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
        req = self._build_request(payload, text)
        try:
            sample_rate, audio = self._infer_audio(req)
        except RuntimeError as exc:
            if not self._should_retry_chunked(exc, req.text):
                raise
            logger.warning(
                "Render hit CUDA OOM in compile mode, retrying with chunked synthesis | chars=%s | chunk_chars=%s",
                len(req.text),
                self.settings.oom_retry_chunk_chars,
            )
            self._recover_after_oom()
            sample_rate, audio = self._synthesize_chunked(payload, req.text)

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

    def _build_request(self, payload: dict, text: str) -> ServeTTSRequest:
        return ServeTTSRequest(
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

    def _infer_audio(self, req: ServeTTSRequest):
        sample_rate = 44_100
        audio = None
        for result in self.engine.inference(req):
            if result.code == "error":
                raise RuntimeError(str(result.error or "Inference error"))
            if result.code == "final" and result.audio:
                sample_rate, audio = result.audio

        if audio is None:
            raise RuntimeError("No audio generated")
        return sample_rate, audio

    def _synthesize_chunked(self, payload: dict, text: str):
        segments = self._split_text(text, self.settings.oom_retry_chunk_chars)
        if len(segments) <= 1:
            raise RuntimeError("CUDA out of memory and chunked retry could not split the text safely")

        sample_rate = 44_100
        audio_segments = []
        for segment in segments:
            req = self._build_request(payload, segment)
            sample_rate, audio = self._infer_audio(req)
            audio_segments.append(audio)

        stitched = concatenate_audio_segments(
            audio_segments,
            sample_rate=sample_rate,
            silence_ms=self.settings.chunk_join_silence_ms,
        )
        return sample_rate, stitched

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

    def _recover_after_oom(self) -> None:
        gc.collect()
        if self._device.startswith("cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()

    def _configure_compile_runtime(self, compile_enabled: bool) -> None:
        if not compile_enabled:
            return
        try:
            import torch._inductor.config as inductor_config

            triton_cfg = getattr(inductor_config, "triton", None)
            if triton_cfg is not None and hasattr(triton_cfg, "cudagraphs"):
                triton_cfg.cudagraphs = self.settings.compile_cudagraphs
                logger.info("Torch compile settings | cudagraphs=%s", self.settings.compile_cudagraphs)
        except Exception:
            logger.debug("Unable to configure torch.compile runtime options", exc_info=True)

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

    def _should_retry_chunked(self, exc: RuntimeError, text: str) -> bool:
        return self._compile_enabled and len(text) > self.settings.oom_retry_chunk_chars and self._is_cuda_oom(exc)

    @staticmethod
    def _is_cuda_oom(exc: BaseException) -> bool:
        message = str(exc).lower()
        return "cuda out of memory" in message or "outofmemoryerror" in message

    def _split_text(self, text: str, max_chars: int) -> list[str]:
        compact = re.sub(r"\s+", " ", text).strip()
        if len(compact) <= max_chars:
            return [compact]

        parts = [piece.strip() for piece in re.split(r"(?<=[.!?…])\s+", compact) if piece.strip()]
        if len(parts) == 1:
            parts = [piece.strip() for piece in re.split(r"(?<=[,;:])\s+", compact) if piece.strip()]

        chunks: list[str] = []
        current = ""

        def flush() -> None:
            nonlocal current
            if current:
                chunks.append(current.strip())
                current = ""

        for part in parts:
            if len(part) > max_chars:
                flush()
                words = part.split()
                line = ""
                for word in words:
                    candidate = f"{line} {word}".strip()
                    if line and len(candidate) > max_chars:
                        chunks.append(line.strip())
                        line = word
                    else:
                        line = candidate
                if line:
                    chunks.append(line.strip())
                continue

            candidate = f"{current} {part}".strip()
            if current and len(candidate) > max_chars:
                flush()
                current = part
            else:
                current = candidate

        flush()
        return chunks or [compact]


class VllmOmniRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._ready = False
        self._error = ""
        self._active_model_source = settings.vllm_omni_model
        self._active_model_path = str(settings.model_path)

    async def startup(self):
        async with self._lock:
            self._error = ""
            try:
                await self._start_server(self._active_model_source, self._active_model_path)
            except Exception as exc:
                self._error = str(exc)
                logger.exception("Managed vllm-omni startup failed")

    async def shutdown(self):
        async with self._lock:
            self._ready = False
            await self._stop_server()

    async def switch_model(self, model_path: str) -> dict:
        async with self._lock:
            target = str(model_path or "").strip()
            if not target:
                raise ValueError("Model path is required.")

            previous_source = self._active_model_source
            previous_path = self._active_model_path
            self._error = ""
            try:
                await self._start_server(target, target)
            except Exception as exc:
                self._error = str(exc)
                logger.exception("Managed vllm-omni model switch failed")
                if previous_source and previous_source != target:
                    try:
                        await self._start_server(previous_source, previous_path)
                        self._error = ""
                    except Exception as restore_exc:
                        self._error = str(restore_exc)
                raise RuntimeError(self._error) from exc

        return self.status()

    def status(self) -> dict:
        ready, detail = self._backend_ready()
        self._ready = ready
        if detail:
            self._error = detail
        return {
            "active_model_path": self._active_model_path,
            "ready": ready,
            "engine": "vllm-omni",
            "compile_enabled": False,
            "dtype": self.settings.dtype,
            "device": self.settings.device,
            "supported_request_fields": [
                "text",
                "voice",
                "reference_id",
                "references",
                "speed",
                "temperature",
                "top_p",
                "seed",
                "language",
                "instructions",
                "max_new_tokens",
                "initial_codec_chunk_frames",
                "x_vector_only_mode",
            ],
            "defaults": {
                "voice": "default",
                "speed": 1.0,
                "temperature": self.settings.temperature,
                "top_p": self.settings.top_p,
                "seed": self.settings.seed,
                "language": "auto",
                "instructions": "",
                "max_new_tokens": 1024,
                "initial_codec_chunk_frames": 6,
                "x_vector_only_mode": False,
            },
            "backend_url": self._base_url,
            "detail": detail or self._error,
        }

    def synthesize(self, payload: dict) -> bytes:
        self._ensure_backend_available()

        text = str(payload.get("text", ""))
        if not text.strip():
            raise ValueError("Text must not be empty")
        if self.settings.max_text_length > 0 and len(text) > self.settings.max_text_length:
            raise ValueError(f"Text is too long for render runtime: {len(text)} > {self.settings.max_text_length}")

        request_payload = self._build_request(payload, text)
        try:
            with httpx.Client(timeout=3600) as client:
                response = client.post(f"{self._base_url}/v1/audio/speech", json=request_payload)
        except httpx.HTTPError as exc:
            self._ready = False
            self._error = f"Managed vllm-omni backend is unreachable: {exc}"
            raise RuntimeError(self._error) from exc
        if response.status_code >= 400:
            detail = response.text
            try:
                detail = response.json().get("detail") or detail
            except Exception:
                pass
            raise RuntimeError(detail or "vllm-omni synthesis failed")
        return response.content

    @property
    def _base_url(self) -> str:
        return f"http://{self.settings.vllm_omni_host}:{self.settings.vllm_omni_port}"

    async def _start_server(self, model_source: str, display_path: str) -> None:
        await self._stop_server()
        self._ready = False
        target = self._normalize_model_source(model_source)
        env = os.environ.copy()
        env.setdefault("FLASHINFER_DISABLE_VERSION_CHECK", "1")
        env["FISH_SPEECH_VLLM_OMNI_DAC_COMPAT"] = "1"
        current_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = f"/app/app:{current_pythonpath}" if current_pythonpath else "/app/app"
        command = self._command(target)
        logger.info("Starting managed vllm-omni | model=%s | command=%s", target, " ".join(command))
        self._process = subprocess.Popen(command, cwd="/app", env=env)
        try:
            await self._wait_until_ready()
        except Exception:
            await self._stop_server()
            raise
        self._active_model_source = target
        self._active_model_path = str(display_path)
        self._ready = True
        logger.info("Managed vllm-omni ready | model=%s", target)

    async def _stop_server(self) -> None:
        proc = self._process
        self._process = None
        if proc is None:
            return
        if proc.poll() is not None:
            return
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, timeout=20)
        except subprocess.TimeoutExpired:
            logger.warning("Managed vllm-omni did not stop gracefully, killing it")
            proc.kill()
            await asyncio.to_thread(proc.wait, timeout=10)

    async def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + max(self.settings.vllm_omni_start_timeout, 30)
        last_error = ""
        while time.monotonic() < deadline:
            proc = self._process
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"Managed vllm-omni exited with code {proc.returncode}")
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.get(f"{self._base_url}/v1/models")
                if response.status_code < 400:
                    return
                last_error = f"/v1/models returned {response.status_code}"
            except Exception as exc:
                last_error = str(exc)
            await asyncio.sleep(2)
        raise RuntimeError(f"Timed out waiting for managed vllm-omni to become ready: {last_error or 'no response'}")

    def _command(self, model_source: str) -> list[str]:
        stage_configs = str(self.settings.vllm_omni_stage_configs_path).strip()
        if not stage_configs:
            raise ValueError("VLLM_OMNI_STAGE_CONFIGS_PATH must not be empty")
        command = [
            "vllm-omni",
            "serve",
            model_source,
            "--host",
            self.settings.vllm_omni_host,
            "--port",
            str(self.settings.vllm_omni_port),
            "--stage-configs-path",
            stage_configs,
            "--gpu-memory-utilization",
            str(self.settings.vllm_omni_gpu_memory_utilization),
            "--trust-remote-code",
            "--enforce-eager",
            "--omni",
        ]
        extra_args = str(self.settings.vllm_omni_extra_args or "").strip()
        if extra_args:
            command.extend(shlex.split(extra_args))
        return command

    def _backend_ready(self) -> tuple[bool, str]:
        proc = self._process
        if proc is not None and proc.poll() is not None:
            return False, f"Managed vllm-omni exited with code {proc.returncode}"
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self._base_url}/v1/models")
            if response.status_code < 400:
                return True, ""
            return False, f"Managed vllm-omni readiness probe returned {response.status_code}"
        except Exception as exc:
            return False, f"Managed vllm-omni backend is unreachable: {exc}"

    def _ensure_backend_available(self) -> None:
        ready, detail = self._backend_ready()
        if ready:
            self._ready = True
            self._error = ""
            return

        with self._sync_lock:
            ready, detail = self._backend_ready()
            if ready:
                self._ready = True
                self._error = ""
                return
            logger.warning("Managed vllm-omni is down, attempting restart | detail=%s", detail)
            self._restart_server_blocking(self._active_model_source, self._active_model_path)
            ready, detail = self._backend_ready()
            if not ready:
                self._ready = False
                self._error = detail
                raise RuntimeError(detail)
            self._ready = True
            self._error = ""

    def _restart_server_blocking(self, model_source: str, display_path: str) -> None:
        proc = self._process
        self._process = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

        target = self._normalize_model_source(model_source)
        env = os.environ.copy()
        env.setdefault("FLASHINFER_DISABLE_VERSION_CHECK", "1")
        env["FISH_SPEECH_VLLM_OMNI_DAC_COMPAT"] = "1"
        current_pythonpath = env.get("PYTHONPATH", "").strip()
        env["PYTHONPATH"] = f"/app/app:{current_pythonpath}" if current_pythonpath else "/app/app"
        command = self._command(target)
        self._process = subprocess.Popen(command, cwd="/app", env=env)
        deadline = time.monotonic() + max(self.settings.vllm_omni_start_timeout, 30)
        last_error = ""
        while time.monotonic() < deadline:
            proc = self._process
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"Managed vllm-omni exited with code {proc.returncode}")
            try:
                with httpx.Client(timeout=10) as client:
                    response = client.get(f"{self._base_url}/v1/models")
                if response.status_code < 400:
                    self._active_model_source = target
                    self._active_model_path = str(display_path)
                    self._ready = True
                    self._error = ""
                    return
                last_error = f"/v1/models returned {response.status_code}"
            except Exception as exc:
                last_error = str(exc)
            time.sleep(2)
        raise RuntimeError(f"Timed out waiting for managed vllm-omni to restart: {last_error or 'no response'}")

    def _build_request(self, payload: dict, text: str) -> dict:
        request_payload: dict[str, Any] = {
            "input": text,
            "response_format": "wav",
        }

        voice = str(payload.get("voice") or "").strip()
        if voice:
            request_payload["voice"] = voice

        for key, caster in (
            ("speed", float),
            ("temperature", float),
            ("top_p", float),
            ("seed", int),
            ("max_new_tokens", int),
            ("initial_codec_chunk_frames", int),
        ):
            value = payload.get(key)
            if value is not None:
                request_payload[key] = caster(value)

        for key in ("language", "instructions", "task_type"):
            value = payload.get(key)
            if value is not None:
                request_payload[key] = value

        if payload.get("x_vector_only_mode") is not None:
            request_payload["x_vector_only_mode"] = bool(payload.get("x_vector_only_mode"))

        reference = self._resolve_reference(payload)
        if reference:
            request_payload["ref_audio"] = reference["audio"]
            request_payload["ref_text"] = reference["text"]
            request_payload.setdefault("task_type", "Base")

        return request_payload

    def _resolve_reference(self, payload: dict) -> dict[str, str] | None:
        reference_id = str(payload.get("reference_id") or "").strip()
        if reference_id:
            return self._saved_reference(reference_id)

        refs = payload.get("references") or []
        if not refs:
            return None
        first = refs[0]
        if not isinstance(first, dict):
            raise ValueError("Explicit references must be objects")

        explicit_reference_id = str(first.get("reference_id") or "").strip()
        if explicit_reference_id:
            return self._saved_reference(explicit_reference_id)

        text = str(first.get("text") or first.get("transcript") or first.get("ref_text") or "").strip()
        if not text:
            raise ValueError("Explicit reference must include text/transcript/ref_text")

        audio = (
            first.get("ref_audio")
            or first.get("audio")
            or first.get("audio_url")
            or first.get("url")
            or first.get("audio_base64")
            or first.get("audio_b64")
        )
        if not audio and first.get("audio_path"):
            audio = self._file_to_data_url(Path(str(first["audio_path"])))
        if not audio:
            raise ValueError("Explicit reference must include ref_audio/audio/audio_url/audio_path")

        return {"audio": self._normalize_audio_reference(audio, first.get("mime_type")), "text": text}

    def _saved_reference(self, reference_id: str) -> dict[str, str]:
        reference_dir = self.settings.references_root / reference_id
        if not reference_dir.exists():
            raise ValueError(f"Reference does not exist: {reference_id}")

        audio_path = next(
            (path for path in sorted(reference_dir.iterdir()) if path.suffix.lower() in AUDIO_EXTENSIONS),
            None,
        )
        if audio_path is None:
            raise ValueError(f"Reference audio does not exist: {reference_id}")

        transcript_path = reference_dir / "sample.lab"
        if not transcript_path.exists():
            raise ValueError(f"Reference transcript does not exist: {reference_id}")
        transcript = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        if not transcript:
            raise ValueError(f"Reference transcript is empty: {reference_id}")

        return {"audio": self._file_to_data_url(audio_path), "text": transcript}

    def _normalize_audio_reference(self, audio: Any, mime_type: Any = None) -> str:
        value = str(audio or "").strip()
        if not value:
            raise ValueError("Reference audio must not be empty")
        if value.startswith("data:"):
            return value
        if "://" in value:
            return value
        base64.b64decode(value, validate=True)
        mime = str(mime_type or "audio/wav").strip() or "audio/wav"
        return f"data:{mime};base64,{value}"

    def _file_to_data_url(self, path: Path) -> str:
        if not path.exists():
            raise ValueError(f"Reference audio path does not exist: {path}")
        mime = AUDIO_MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    @staticmethod
    def _normalize_model_source(model_source: str) -> str:
        target = str(model_source or "").strip()
        if not target:
            raise ValueError("Model path is required.")
        return target


def create_runtime(settings: Settings | None = None) -> RenderRuntime:
    runtime_settings = settings or load_settings()
    engine = runtime_settings.render_engine
    if engine in {"fish", ""}:
        return FishRuntime(runtime_settings)
    if engine in {"vllm-omni", "vllm_omni", "vllm"}:
        return VllmOmniRuntime(runtime_settings)
    raise ValueError(f"Unsupported render engine: {runtime_settings.render_engine}")
