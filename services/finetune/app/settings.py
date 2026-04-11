from dataclasses import dataclass
from pathlib import Path
import os

from shared.config import app_paths, ensure_dirs


@dataclass(frozen=True)
class Settings:
    model_repo: str
    model_path: Path
    hf_endpoint: str | None
    finetuned_root: Path
    training_root: Path
    logs_root: Path

    def ensure_dirs(self) -> None:
        ensure_dirs(self.finetuned_root, self.training_root, self.logs_root)


def load_settings() -> Settings:
    paths = app_paths()
    return Settings(
        model_repo=os.getenv("MODEL_REPO", "fishaudio/s2-pro"),
        model_path=Path(os.getenv("MODEL_PATH", "/app/data/checkpoints/s2-pro")),
        hf_endpoint=os.getenv("HF_ENDPOINT") or None,
        finetuned_root=paths["finetuned_root"],
        training_root=paths["training_root"],
        logs_root=paths["logs_root"],
    )
