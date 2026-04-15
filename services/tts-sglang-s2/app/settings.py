from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shlex


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


@dataclass(frozen=True)
class Settings:
    model_path: str
    model_name: str
    config_path: Path
    references_root: Path

    backend_url: str
    manage_backend: bool
    backend_host: str
    backend_port: int
    backend_log_level: str
    sgl_omni_bin: str
    sgl_omni_extra_args: str
    startup_timeout: int
    request_timeout: int

    warmup_enabled: bool
    warmup_text: str
    warmup_max_new_tokens: int

    target_first_byte_ms: int
    early_wav_header: bool
    stream_sample_rate: int
    stream_channels: int
    stream_bits_per_sample: int

    temperature: float
    top_p: float
    top_k: int
    repetition_penalty: float
    seed: int | None
    max_new_tokens: int

    def backend_command(self) -> list[str]:
        command = [
            self.sgl_omni_bin,
            "serve",
            "--model-path",
            self.model_path,
            "--config",
            str(self.config_path),
            "--host",
            self.backend_host,
            "--port",
            str(self.backend_port),
            "--model-name",
            self.model_name,
            "--log-level",
            self.backend_log_level,
        ]
        if self.sgl_omni_extra_args.strip():
            command.extend(shlex.split(self.sgl_omni_extra_args))
        return command


def load_settings() -> Settings:
    backend_host = os.getenv("SGLANG_S2_BACKEND_HOST", "127.0.0.1")
    backend_port = _int_env("SGLANG_S2_BACKEND_PORT", 8092)
    backend_url = os.getenv("SGLANG_S2_BACKEND_URL", f"http://{backend_host}:{backend_port}").rstrip("/")
    manage_default = os.getenv("SGLANG_S2_BACKEND_URL") is None
    seed = os.getenv("SEED")

    return Settings(
        model_path=os.getenv("SGLANG_S2_MODEL_PATH", os.getenv("MODEL_PATH", "fishaudio/s2-pro")),
        model_name=os.getenv("SGLANG_S2_MODEL_NAME", "fishaudio-s2-low-ttfb"),
        config_path=Path(os.getenv("SGLANG_S2_CONFIG_PATH", "/app/config/s2pro_low_ttfb.yaml")),
        references_root=Path(os.getenv("REFERENCES_ROOT", "/app/references")),
        backend_url=backend_url,
        manage_backend=_bool_env("SGLANG_S2_MANAGE_BACKEND", manage_default),
        backend_host=backend_host,
        backend_port=backend_port,
        backend_log_level=os.getenv("SGLANG_S2_BACKEND_LOG_LEVEL", "info"),
        sgl_omni_bin=os.getenv("SGLANG_OMNI_BIN", "sgl-omni"),
        sgl_omni_extra_args=os.getenv("SGLANG_S2_EXTRA_ARGS", ""),
        startup_timeout=_int_env("SGLANG_S2_STARTUP_TIMEOUT", 2400),
        request_timeout=_int_env("SGLANG_S2_REQUEST_TIMEOUT", 3600),
        warmup_enabled=_bool_env("SGLANG_S2_WARMUP", True),
        warmup_text=os.getenv("SGLANG_S2_WARMUP_TEXT", "Warm up the low latency speech stream."),
        warmup_max_new_tokens=_int_env("SGLANG_S2_WARMUP_MAX_NEW_TOKENS", 32),
        target_first_byte_ms=_int_env("SGLANG_S2_TARGET_FIRST_BYTE_MS", 200),
        early_wav_header=_bool_env("SGLANG_S2_EARLY_WAV_HEADER", True),
        stream_sample_rate=_int_env("SGLANG_S2_STREAM_SAMPLE_RATE", 44100),
        stream_channels=_int_env("SGLANG_S2_STREAM_CHANNELS", 1),
        stream_bits_per_sample=_int_env("SGLANG_S2_STREAM_BITS_PER_SAMPLE", 16),
        temperature=_float_env("TEMPERATURE", 0.8),
        top_p=_float_env("TOP_P", 0.8),
        top_k=_int_env("TOP_K", 30),
        repetition_penalty=_float_env("REPETITION_PENALTY", 1.1),
        seed=int(seed) if seed else None,
        max_new_tokens=_int_env("SGLANG_S2_MAX_NEW_TOKENS", 1024),
    )
