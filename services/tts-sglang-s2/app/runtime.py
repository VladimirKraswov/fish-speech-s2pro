from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import subprocess
import time
from typing import Any

import httpx

from .settings import Settings

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac"}


class SGLangS2Runtime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._lock = asyncio.Lock()
        self._process: subprocess.Popen | None = None
        self._ready = False
        self._error = ""
        self._last_warmup_ms: float | None = None

    @property
    def ready(self) -> bool:
        return self._ready

    async def startup(self) -> None:
        async with self._lock:
            self._ready = False
            self._error = ""
            try:
                if self.settings.manage_backend:
                    await self._start_backend()
                else:
                    await self._wait_until_ready()
                if self.settings.warmup_enabled:
                    await self._warmup_streaming_path()
                self._ready = True
            except Exception as exc:
                self._error = str(exc)
                logger.exception("SGLang S2 runtime startup failed")
                if self.settings.manage_backend:
                    await self._stop_backend()

    async def shutdown(self) -> None:
        async with self._lock:
            self._ready = False
            await self._stop_backend()

    async def status(self) -> dict[str, Any]:
        ready, detail = await self._backend_ready()
        self._ready = ready
        if detail:
            self._error = detail
        return {
            "active_model_path": self.settings.model_path,
            "ready": ready,
            "engine": "sglang-omni-s2",
            "backend_url": self.settings.backend_url,
            "managed_backend": self.settings.manage_backend,
            "model_name": self.settings.model_name,
            "target_first_byte_ms": self.settings.target_first_byte_ms,
            "early_wav_header": self.settings.early_wav_header,
            "last_warmup_ms": round(self._last_warmup_ms, 1) if self._last_warmup_ms is not None else None,
            "supported_output_formats": ["wav"],
            "supported_request_fields": [
                "text",
                "input",
                "voice",
                "reference_id",
                "references",
                "ref_audio",
                "ref_text",
                "speed",
                "temperature",
                "top_p",
                "top_k",
                "repetition_penalty",
                "seed",
                "max_new_tokens",
                "language",
                "instructions",
                "task_type",
                "stage_params",
            ],
            "defaults": {
                "voice": "default",
                "response_format": "wav",
                "speed": 1.0,
                "temperature": self.settings.temperature,
                "top_p": self.settings.top_p,
                "top_k": self.settings.top_k,
                "repetition_penalty": self.settings.repetition_penalty,
                "seed": self.settings.seed,
                "max_new_tokens": self.settings.max_new_tokens,
            },
            "detail": detail or self._error,
        }

    async def synthesize(self, payload: dict[str, Any]) -> tuple[bytes, str]:
        request_payload = self.build_speech_payload(payload, stream=False)
        timeout = self._timeout()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(f"{self.settings.backend_url}/v1/audio/speech", json=request_payload)
        except httpx.HTTPError as exc:
            self._ready = False
            self._error = f"SGLang Omni backend is unreachable: {exc}"
            raise RuntimeError(self._error) from exc
        if response.status_code >= 400:
            raise RuntimeError(self._error_detail(response))
        return response.content, response.headers.get("content-type", "audio/wav")

    async def open_sse_stream(self, payload: dict[str, Any]) -> tuple[httpx.AsyncClient, httpx.Response]:
        request_payload = self.build_speech_payload(payload, stream=True)
        client = httpx.AsyncClient(timeout=self._timeout())
        request = client.build_request("POST", f"{self.settings.backend_url}/v1/audio/speech", json=request_payload)
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            self._ready = False
            self._error = f"SGLang Omni backend is unreachable: {exc}"
            raise RuntimeError(self._error) from exc
        if response.status_code >= 400:
            detail = await self._async_error_detail(response)
            await response.aclose()
            await client.aclose()
            raise RuntimeError(detail)
        return client, response

    def build_speech_payload(self, payload: dict[str, Any], *, stream: bool) -> dict[str, Any]:
        text = str(payload.get("input") or payload.get("text") or "").strip()
        if not text:
            raise ValueError("Text must not be empty")

        response_format = str(payload.get("response_format") or "wav").strip().lower()
        if response_format != "wav":
            raise ValueError("Only response_format='wav' is supported by the low-TTFB WAV proxy")

        request: dict[str, Any] = {
            "model": payload.get("model") or self.settings.model_name,
            "input": text,
            "voice": str(payload.get("voice") or "default"),
            "response_format": "wav",
            "speed": float(_payload_value(payload, "speed", 1.0)),
            "stream": stream,
            "temperature": float(_payload_value(payload, "temperature", self.settings.temperature)),
            "top_p": float(_payload_value(payload, "top_p", self.settings.top_p)),
            "top_k": int(_payload_value(payload, "top_k", self.settings.top_k)),
            "repetition_penalty": float(_payload_value(payload, "repetition_penalty", self.settings.repetition_penalty)),
            "max_new_tokens": int(_payload_value(payload, "max_new_tokens", self.settings.max_new_tokens)),
        }

        seed = payload.get("seed", self.settings.seed)
        if seed is not None:
            request["seed"] = int(seed)

        for key in ("language", "instructions", "task_type", "stage_params"):
            value = payload.get(key)
            if value is not None:
                request[key] = value

        references = self._build_references(payload)
        if references:
            request["references"] = references

        return request

    async def _start_backend(self) -> None:
        await self._stop_backend()
        if not self.settings.config_path.exists():
            raise FileNotFoundError(f"SGLang S2 config does not exist: {self.settings.config_path}")

        env = os.environ.copy()
        env.setdefault("FLASHINFER_DISABLE_VERSION_CHECK", "1")
        env.setdefault("SGLANG_OMNI_STARTUP_TIMEOUT", str(self.settings.startup_timeout))
        command = self.settings.backend_command()
        logger.info("Starting SGLang Omni S2 backend: %s", " ".join(command))
        self._process = subprocess.Popen(command, env=env)
        await self._wait_until_ready()

    async def _stop_backend(self) -> None:
        proc = self._process
        self._process = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            await asyncio.to_thread(proc.wait, timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            await asyncio.to_thread(proc.wait, timeout=10)

    async def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + max(self.settings.startup_timeout, 30)
        last_error = ""
        while time.monotonic() < deadline:
            proc = self._process
            if proc is not None and proc.poll() is not None:
                raise RuntimeError(f"SGLang Omni backend exited with code {proc.returncode}")
            ready, detail = await self._backend_ready()
            if ready:
                return
            last_error = detail
            await asyncio.sleep(2)
        raise RuntimeError(f"Timed out waiting for SGLang Omni backend: {last_error or 'no response'}")

    async def _backend_ready(self) -> tuple[bool, str]:
        proc = self._process
        if proc is not None and proc.poll() is not None:
            return False, f"SGLang Omni backend exited with code {proc.returncode}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.settings.backend_url}/v1/models")
            if response.status_code < 400:
                return True, ""
            return False, f"/v1/models returned {response.status_code}"
        except Exception as exc:
            return False, str(exc)

    async def _warmup_streaming_path(self) -> None:
        payload = {
            "input": self.settings.warmup_text,
            "response_format": "wav",
            "stream": True,
            "max_new_tokens": self.settings.warmup_max_new_tokens,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "top_k": self.settings.top_k,
            "repetition_penalty": self.settings.repetition_penalty,
        }
        started = time.perf_counter()
        seen_audio = False
        logger.info("Warming SGLang S2 streaming path")
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
            async with client.stream("POST", f"{self.settings.backend_url}/v1/audio/speech", json=payload) as response:
                if response.status_code >= 400:
                    raise RuntimeError(await self._async_error_detail(response))
                async for line in response.aiter_lines():
                    data = _sse_data(line)
                    if data is None:
                        continue
                    if data == "[DONE]":
                        break
                    chunk = _decode_sse_audio(data)
                    if chunk:
                        seen_audio = True
        self._last_warmup_ms = (time.perf_counter() - started) * 1000
        if not seen_audio:
            logger.warning("SGLang S2 streaming warmup finished without an audio chunk")
        logger.info("SGLang S2 streaming warmup completed in %.1f ms", self._last_warmup_ms)

    def _build_references(self, payload: dict[str, Any]) -> list[dict[str, str]]:
        references: list[dict[str, str]] = []

        reference_id = str(payload.get("reference_id") or "").strip()
        if reference_id:
            references.append(self._saved_reference(reference_id))

        ref_audio = payload.get("ref_audio")
        if ref_audio:
            ref_text = str(payload.get("ref_text") or "").strip()
            if not ref_text:
                raise ValueError("ref_text is required when ref_audio is provided")
            references.append({"audio_path": str(ref_audio), "text": ref_text})

        raw_refs = payload.get("references") or []
        if not isinstance(raw_refs, list):
            raise ValueError("references must be a list")

        for item in raw_refs:
            if not isinstance(item, dict):
                raise ValueError("Each reference must be an object")
            item_reference_id = str(item.get("reference_id") or "").strip()
            if item_reference_id:
                references.append(self._saved_reference(item_reference_id))
                continue

            audio_path = item.get("audio_path") or item.get("ref_audio") or item.get("audio_url") or item.get("url")
            text = str(item.get("text") or item.get("transcript") or item.get("ref_text") or "").strip()
            if audio_path is None and item.get("audio"):
                audio_path = item["audio"]

            vq_codes = item.get("vq_codes")
            if vq_codes is not None:
                ref: dict[str, Any] = {"vq_codes": vq_codes, "text": text}
                references.append(ref)
                continue

            if audio_path is None:
                raise ValueError("Reference must include audio_path/ref_audio/audio_url/url/audio or vq_codes")
            if not text:
                raise ValueError("Reference must include text/transcript/ref_text")
            audio_value = str(audio_path).strip()
            if audio_value.startswith("data:"):
                raise ValueError("SGLang S2 references must use local paths, HTTP URLs, or vq_codes; data URLs are not supported")
            references.append({"audio_path": audio_value, "text": text})

        return references

    def _saved_reference(self, reference_id: str) -> dict[str, str]:
        reference_dir = self.settings.references_root / reference_id
        if not reference_dir.exists():
            raise ValueError(f"Reference does not exist: {reference_id}")

        transcript_path = reference_dir / "sample.lab"
        if not transcript_path.exists():
            raise ValueError(f"Reference transcript does not exist: {reference_id}")
        transcript = transcript_path.read_text(encoding="utf-8", errors="replace").strip()
        if not transcript:
            raise ValueError(f"Reference transcript is empty: {reference_id}")

        sample_path = reference_dir / "sample.wav"
        audio_path = sample_path if sample_path.exists() else None
        if audio_path is None:
            audio_path = next(
                (
                    path
                    for path in sorted(reference_dir.iterdir())
                    if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
                ),
                None,
            )
        if audio_path is None:
            raise ValueError(f"Reference audio does not exist: {reference_id}")

        return {"audio_path": str(audio_path), "text": transcript}

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(self.settings.request_timeout, connect=30, write=30, pool=30)

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            data = response.json()
            return str(data.get("detail") or data)
        except Exception:
            return response.text or f"Upstream returned {response.status_code}"

    @staticmethod
    async def _async_error_detail(response: httpx.Response) -> str:
        content = await response.aread()
        try:
            data = json.loads(content.decode("utf-8", errors="replace"))
            return str(data.get("detail") or data)
        except Exception:
            return content.decode("utf-8", errors="replace") or f"Upstream returned {response.status_code}"


def _sse_data(line: str) -> str | None:
    if not line:
        return None
    if not line.startswith("data:"):
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


def _payload_value(payload: dict[str, Any], key: str, default: Any) -> Any:
    value = payload.get(key)
    return default if value is None else value
