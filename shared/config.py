from pathlib import Path

def app_paths() -> dict[str, Path]:
    return {
        "checkpoints_root": Path("/app/data/checkpoints"),
        "finetuned_root": Path("/app/data/finetuned"),
        "training_root": Path("/app/data/training_data"),
        "references_root": Path("/app/references"),
        "logs_root": Path("/app/data/finetuned/logs"),
    }

def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)