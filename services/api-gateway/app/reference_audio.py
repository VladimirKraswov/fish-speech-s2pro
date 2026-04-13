from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    if not ffmpeg_available():
        return None

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return None
    try:
        return float((result.stdout or "").strip())
    except ValueError:
        return None


def normalize_reference_audio(
    source: Path,
    target: Path,
    *,
    max_seconds: int,
    sample_rate: int,
    channels: int,
) -> dict:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg/ffprobe are required to prepare reference audio.")

    duration_before = probe_duration(source)
    target.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-t",
        str(max_seconds),
        "-c:a",
        "pcm_s16le",
        str(target),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg failed").strip())

    duration_after = probe_duration(target)
    trimmed = bool(duration_before and duration_before > max_seconds + 0.05)
    return {
        "normalized": True,
        "source_name": source.name,
        "audio_file": target.name,
        "duration_sec": round(duration_after, 3) if duration_after else None,
        "original_duration_sec": round(duration_before, 3) if duration_before else None,
        "trimmed": trimmed,
        "max_seconds": max_seconds,
        "sample_rate": sample_rate,
        "channels": channels,
    }


def load_reference_meta(path: Path) -> dict:
    meta_path = path / "reference.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_reference_meta(path: Path, meta: dict) -> None:
    (path / "reference.json").write_text(json.dumps(meta, ensure_ascii=True, indent=2), encoding="utf-8")
