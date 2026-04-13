from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from .filesystem import AUDIO_EXTENSIONS, ensure_name, save_upload


REFERENCE_EXTENSIONS = AUDIO_EXTENSIONS | {".aac", ".m4a", ".mp4", ".ogg", ".wav"}


def ensure_upload_name(filename: str) -> str:
    name = Path(ensure_name(Path(filename or "").name, "File name"))
    if name.suffix.lower() not in REFERENCE_EXTENSIONS:
        raise ValueError(f"Unsupported audio file type: {name.suffix}")
    return name.name


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_duration(path: Path) -> float | None:
    if not path.exists() or not ffmpeg_available():
        return None
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
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
    result = subprocess.run(
        [
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
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "ffmpeg failed").strip())

    duration_after = probe_duration(target)
    trimmed = bool(duration_before and duration_before > max_seconds + 0.05)
    return {
        "normalized": True,
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
    (path / "reference.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


class ReferenceStore:
    def __init__(self, root: Path, *, max_seconds: int = 12, sample_rate: int = 24000, channels: int = 1) -> None:
        self.root = root
        self.max_seconds = max_seconds
        self.sample_rate = sample_rate
        self.channels = channels
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        return [self.get(path.name) for path in sorted(self.root.iterdir()) if path.is_dir()]

    def get(self, name: str) -> dict:
        path = self._dir(name)
        audio = self.audio_path(name)
        meta = load_reference_meta(path)
        transcript_path = path / "sample.lab"
        return {
            "name": path.name,
            "display_name": meta.get("display_name", path.name),
            "audio_file": audio.name if audio else None,
            "audio_url": f"/api/references/{path.name}/audio" if audio else None,
            "transcript": transcript_path.read_text(encoding="utf-8", errors="replace") if transcript_path.exists() else "",
            "language": meta.get("language", "en"),
            "kind": meta.get("kind", "upload"),
            "reference_meta": meta,
        }

    def save(self, name: str, audio, transcript: str, language: str, replace: bool) -> dict:
        path = self._dir(name, create=True)
        transcript_text = transcript.strip()
        if not transcript_text:
            raise ValueError("Reference transcript is required.")
        if language not in {"en", "zh"}:
            raise ValueError("Only English and Chinese reference transcripts are supported in this demo.")
        if path.exists() and any(path.iterdir()) and not replace:
            raise ValueError("Reference already exists. Enable replace or delete it first.")

        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

        upload_name = ensure_upload_name(audio.filename)
        source_target = path / f"upload{Path(upload_name).suffix.lower()}"
        output_target = path / "sample.wav"

        save_upload(audio, source_target)
        meta = normalize_reference_audio(
            source_target,
            output_target,
            max_seconds=self.max_seconds,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        source_target.unlink(missing_ok=True)
        (path / "sample.lab").write_text(transcript_text, encoding="utf-8")
        meta.update({"kind": "upload", "language": language, "display_name": name})
        save_reference_meta(path, meta)
        return self.get(name)

    def create_demo(self, name: str, transcript: str, *, language: str, voice: str) -> dict:
        path = self._dir(name, create=True)
        output_target = path / "sample.wav"
        transcript_path = path / "sample.lab"

        if output_target.exists() and transcript_path.exists():
            meta = load_reference_meta(path)
            meta.update({"kind": "builtin-demo", "language": language, "display_name": "Built-in Demo Voice"})
            save_reference_meta(path, meta)
            return self.get(name)

        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)

        source_target = path / "source.wav"
        result = subprocess.run(
            ["espeak-ng", "-v", voice, "-s", "145", "-w", str(source_target), transcript],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "espeak-ng failed").strip())

        meta = normalize_reference_audio(
            source_target,
            output_target,
            max_seconds=self.max_seconds,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        source_target.unlink(missing_ok=True)
        transcript_path.write_text(transcript, encoding="utf-8")
        meta.update({"kind": "builtin-demo", "language": language, "display_name": "Built-in Demo Voice"})
        save_reference_meta(path, meta)
        return self.get(name)

    def delete(self, name: str) -> dict:
        data = self.get(name)
        if data["kind"] == "builtin-demo":
            raise ValueError("The built-in demo reference cannot be deleted.")
        shutil.rmtree(self._dir(name))
        return {"deleted": True, "reference": data}

    def audio_path(self, name: str) -> Path | None:
        path = self._dir(name)
        return next((item for item in sorted(path.iterdir()) if item.suffix.lower() in REFERENCE_EXTENSIONS), None)

    def _dir(self, name: str, create: bool = False) -> Path:
        path = self.root / ensure_name(name, "Reference name")
        if not create and not path.exists():
            raise ValueError(f"Reference does not exist: {path.name}")
        return path
