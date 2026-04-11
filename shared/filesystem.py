from pathlib import Path
import re


AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac"}
DATASET_EXTENSIONS = AUDIO_EXTENSIONS | {".lab", ".txt"}


def ensure_name(value: str, label: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", str(value or "").strip()).strip("._-")
    if not name:
        raise ValueError(f"{label} is required.")
    return name


def ensure_file_name(value: str, allowed: set[str]) -> str:
    name = Path(ensure_name(Path(value or "").name, "File name"))
    if name.suffix.lower() not in allowed:
        raise ValueError(f"Unsupported file type: {name.suffix}")
    return name.name


def save_upload(upload, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        while chunk := upload.file.read(1024 * 1024):
            handle.write(chunk)


def sample_rows(path: Path) -> list[dict]:
    rows = {}
    for file in sorted(path.iterdir()):
        stem = file.stem
        rows.setdefault(stem, {"name": stem, "audio_file": None, "transcript": ""})
        if file.suffix.lower() in AUDIO_EXTENSIONS:
            rows[stem]["audio_file"] = file.name
        if file.suffix.lower() == ".lab":
            rows[stem]["transcript"] = file.read_text(encoding="utf-8", errors="replace")
    return list(rows.values())


def file_rows(path: Path) -> list[dict]:
    return [{"name": file.name, "size": file.stat().st_size} for file in sorted(path.iterdir()) if file.is_file()]


def pair_stats(path: Path) -> dict:
    samples = sample_rows(path)
    paired = sum(1 for row in samples if row["audio_file"] and row["transcript"].strip())
    return {"samples": len(samples), "paired": paired}
