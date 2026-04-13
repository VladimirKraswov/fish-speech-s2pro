from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Settings:
    runtime_url: str
    data_root: Path
    references_root: Path
    reference_max_seconds: int
    reference_sample_rate: int
    reference_channels: int
    default_reference_name: str
    default_reference_text: str
    default_reference_language: str
    default_reference_voice: str
    default_target_text: str
    synthesis_timeout_sec: float

    def ensure_dirs(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.references_root.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    return Settings(
        runtime_url=os.getenv("GPTSOVITS_RUNTIME_URL", "http://gptsovits-runtime:9880"),
        data_root=Path(os.getenv("GPTSOVITS_DATA_ROOT", "/app/data")),
        references_root=Path(os.getenv("GPTSOVITS_REFERENCES_ROOT", "/app/references")),
        reference_max_seconds=int(os.getenv("GPTSOVITS_REFERENCE_MAX_SECONDS", "12")),
        reference_sample_rate=int(os.getenv("GPTSOVITS_REFERENCE_SAMPLE_RATE", "24000")),
        reference_channels=int(os.getenv("GPTSOVITS_REFERENCE_CHANNELS", "1")),
        default_reference_name=os.getenv("GPTSOVITS_DEFAULT_REFERENCE_NAME", "demo-english"),
        default_reference_text=os.getenv(
            "GPTSOVITS_DEFAULT_REFERENCE_TEXT",
            "Hello, this is the built in GPT SoVITS version two demo voice for the Docker showcase.",
        ),
        default_reference_language=os.getenv("GPTSOVITS_DEFAULT_REFERENCE_LANGUAGE", "en"),
        default_reference_voice=os.getenv("GPTSOVITS_DEFAULT_REFERENCE_VOICE", "en-us"),
        default_target_text=os.getenv(
            "GPTSOVITS_DEFAULT_TARGET_TEXT",
            "This server is running GPT SoVITS version two inside Docker. Upload your own reference and clone a new voice.",
        ),
        synthesis_timeout_sec=float(os.getenv("GPTSOVITS_SYNTHESIS_TIMEOUT_SEC", "900")),
    )
