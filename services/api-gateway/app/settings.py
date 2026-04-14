from dataclasses import dataclass
from pathlib import Path
import os

from shared.config import app_paths, ensure_dirs


@dataclass(frozen=True)
class Settings:
    render_url: str
    live_url: str
    preprocess_url: str
    finetune_url: str
    model_path: Path
    live_model_path: Path
    live_engine: str
    checkpoints_root: Path
    finetuned_root: Path
    training_root: Path
    references_root: Path
    logs_root: Path
    reference_max_seconds: int
    reference_sample_rate: int
    reference_channels: int

    def ensure_dirs(self) -> None:
        ensure_dirs(self.checkpoints_root, self.finetuned_root, self.training_root, self.references_root, self.logs_root)

    @property
    def live_enabled(self) -> bool:
        return self.live_engine not in {"", "0", "false", "off", "none", "disabled"}


def load_settings() -> Settings:
    paths = app_paths()
    return Settings(
        render_url=os.getenv("RENDER_URL", "http://tts-render:8888"),
        live_url=os.getenv("LIVE_URL", "http://tts-live:8888"),
        preprocess_url=os.getenv("PREPROCESS_URL", "http://text-preprocess:8888"),
        finetune_url=os.getenv("FINETUNE_URL", "http://finetune-api:8888"),
        model_path=Path(os.getenv("MODEL_PATH", "/app/data/checkpoints/s2-pro")),
        live_model_path=Path(os.getenv("LIVE_MODEL_PATH", "/app/data/live_engine/s2-pro-q8_0.gguf")),
        live_engine=os.getenv("LIVE_ENGINE", "s2cpp").lower(),
        checkpoints_root=paths["checkpoints_root"],
        finetuned_root=paths["finetuned_root"],
        training_root=paths["training_root"],
        references_root=paths["references_root"],
        logs_root=paths["logs_root"],
        reference_max_seconds=int(os.getenv("REFERENCE_MAX_SECONDS", "30")),
        reference_sample_rate=int(os.getenv("REFERENCE_SAMPLE_RATE", "24000")),
        reference_channels=int(os.getenv("REFERENCE_CHANNELS", "1")),
    )
