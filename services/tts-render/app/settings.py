from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    model_path: Path
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


def load_settings() -> Settings:
    return Settings(
        model_path=Path(os.getenv("MODEL_PATH", "/app/data/checkpoints/s2-pro")),
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
    )
