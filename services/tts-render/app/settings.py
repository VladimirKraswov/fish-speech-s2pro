from dataclasses import dataclass
from pathlib import Path
import os
import sys


@dataclass(frozen=True)
class Settings:
    render_engine: str
    model_path: Path
    references_root: Path
    device: str
    dtype: str
    enable_compile: bool
    compile_cudagraphs: bool
    max_text_length: int
    chunk_length: int
    normalize: bool
    use_memory_cache: str
    temperature: float
    top_p: float
    repetition_penalty: float
    seed: int | None
    oom_retry_chunk_chars: int
    chunk_join_silence_ms: int
    vllm_omni_host: str
    vllm_omni_port: int
    vllm_omni_gpu_memory_utilization: float
    vllm_omni_stage_configs_path: str
    vllm_omni_extra_args: str
    vllm_omni_start_timeout: int


def load_settings() -> Settings:
    py_ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    default_stage_config = (
        Path("/opt/venv")
        / "lib"
        / py_ver
        / "site-packages"
        / "vllm_omni"
        / "model_executor"
        / "stage_configs"
        / "fish_speech_s2_pro.yaml"
    )
    return Settings(
        render_engine=os.getenv("RENDER_ENGINE", "fish").strip().lower(),
        model_path=Path(os.getenv("MODEL_PATH", "/app/data/checkpoints/s2-pro")),
        references_root=Path(os.getenv("REFERENCES_ROOT", "/app/references")),
        device=os.getenv("DEVICE", "cuda"),
        dtype=os.getenv("DTYPE", "bfloat16"),
        enable_compile=os.getenv("ENABLE_COMPILE", "false").lower() == "true",
        compile_cudagraphs=os.getenv("COMPILE_CUDAGRAPHS", "false").lower() == "true",
        max_text_length=int(os.getenv("MAX_TEXT_LENGTH", "1500")),
        chunk_length=int(os.getenv("CHUNK_LENGTH", "240")),
        normalize=os.getenv("NORMALIZE_TEXT", "true").lower() == "true",
        use_memory_cache=os.getenv("USE_MEMORY_CACHE", "on"),
        temperature=float(os.getenv("TEMPERATURE", "0.62")),
        top_p=float(os.getenv("TOP_P", "0.88")),
        repetition_penalty=float(os.getenv("REPETITION_PENALTY", "1.15")),
        seed=int(os.getenv("SEED")) if os.getenv("SEED") else None,
        oom_retry_chunk_chars=int(os.getenv("OOM_RETRY_CHUNK_CHARS", "140")),
        chunk_join_silence_ms=int(os.getenv("CHUNK_JOIN_SILENCE_MS", "90")),
        vllm_omni_host=os.getenv("VLLM_OMNI_HOST", "127.0.0.1"),
        vllm_omni_port=int(os.getenv("VLLM_OMNI_PORT", "8091")),
        vllm_omni_gpu_memory_utilization=float(os.getenv("VLLM_OMNI_GPU_MEMORY_UTILIZATION", "0.9")),
        vllm_omni_stage_configs_path=os.getenv("VLLM_OMNI_STAGE_CONFIGS_PATH", "").strip() or str(default_stage_config),
        vllm_omni_extra_args=os.getenv("VLLM_OMNI_EXTRA_ARGS", ""),
        vllm_omni_start_timeout=int(os.getenv("VLLM_OMNI_START_TIMEOUT", "900")),
    )
