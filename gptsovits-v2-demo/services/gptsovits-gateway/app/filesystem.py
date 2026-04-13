from pathlib import Path
import re


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac"}


def ensure_name(value: str, label: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip()).strip("._-")
    if not name:
        raise ValueError(f"{label} is required.")
    return name


def save_upload(upload, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        while chunk := upload.file.read(1024 * 1024):
            handle.write(chunk)
