from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    live_model_path: Path
    s2cpp_bin: Path
    s2cpp_tokenizer_path: Path
    s2cpp_extra_args: str


def load_settings() -> Settings:
    return Settings(
        live_model_path=Path(os.getenv("LIVE_MODEL_PATH", "/app/data/live_engine/s2-pro-q8_0.gguf")),
        s2cpp_bin=Path(os.getenv("S2CPP_BIN", "/app/data/live_engine/s2")),
        s2cpp_tokenizer_path=Path(os.getenv("S2CPP_TOKENIZER_PATH", "/app/data/live_engine/tokenizer.json")),
        s2cpp_extra_args=os.getenv("S2CPP_EXTRA_ARGS", ""),
    )
