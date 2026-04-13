from __future__ import annotations

import base64
from pathlib import Path
import shutil

from shared.filesystem import AUDIO_EXTENSIONS, ensure_file_name, ensure_name, save_upload
from .reference_audio import load_reference_meta, normalize_reference_audio, probe_duration, save_reference_meta


class ReferenceService:
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
        audio = self._audio_file(path)
        lab = path / "sample.lab"
        meta = load_reference_meta(path)
        if audio and "duration_sec" not in meta:
            duration = probe_duration(audio)
            if duration:
                meta["duration_sec"] = round(duration, 3)
        return {
            "name": path.name,
            "path": str(path),
            "audio_file": audio.name if audio else None,
            "transcript": lab.read_text(encoding="utf-8", errors="replace") if lab.exists() else "",
            "reference_meta": meta,
        }

    def save(self, name: str, audio, transcript: str, replace: bool) -> dict:
        path = self._dir(name, create=True)
        transcript_text = transcript.strip()
        if not transcript_text:
            raise ValueError("Reference transcript is required.")
        if not path.exists():
            path.mkdir(parents=True)
        audio_name = ensure_file_name(audio.filename, AUDIO_EXTENSIONS)
        if path.exists() and any(path.iterdir()) and not replace:
            raise ValueError("Reference already exists. Enable replace or delete it first.")
        for existing in path.iterdir():
            if existing.is_file():
                existing.unlink()
        source_target = path / f"upload{Path(audio_name).suffix.lower()}"
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
        save_reference_meta(path, meta)
        return self.get(name)

    def ensure_runtime_ready(self, name: str) -> dict:
        path = self._dir(name)
        audio = self._audio_file(path)
        if not audio:
            raise ValueError(f"Reference audio does not exist: {path.name}")

        meta = load_reference_meta(path)
        normalized_ok = (
            meta.get("normalized") is True
            and meta.get("audio_file") == "sample.wav"
            and int(meta.get("max_seconds", 0) or 0) <= self.max_seconds
            and int(meta.get("sample_rate", 0) or 0) == self.sample_rate
            and int(meta.get("channels", 0) or 0) == self.channels
        )
        if normalized_ok and audio.name == "sample.wav":
            return self.get(name)

        source = audio
        target = path / "sample.normalized.wav"
        new_meta = normalize_reference_audio(
            source,
            target,
            max_seconds=self.max_seconds,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        for existing in path.iterdir():
            if existing.is_file() and existing.name not in {"sample.lab", "reference.json"}:
                existing.unlink()
        target.rename(path / "sample.wav")
        new_meta["audio_file"] = "sample.wav"
        save_reference_meta(path, new_meta)
        return self.get(name)

    def delete(self, name: str) -> dict:
        path = self._dir(name)
        data = self.get(name)
        shutil.rmtree(path)
        return {"deleted": True, "reference": data}

    def audio_path(self, name: str) -> Path:
        path = self._dir(name)
        audio = self._audio_file(path)
        if not audio:
            raise ValueError(f"Reference audio does not exist: {path.name}")
        return audio

    def render_payload(self, name: str) -> dict:
        data = self.get(name)
        audio = self.audio_path(name)
        transcript = str(data.get("transcript", "")).strip()
        if not transcript:
            raise ValueError(f"Reference transcript does not exist: {name}")
        return {
            "audio_b64": base64.b64encode(audio.read_bytes()).decode("ascii"),
            "text": transcript,
        }

    def _dir(self, name: str, create: bool = False) -> Path:
        path = self.root / ensure_name(name, "Reference name")
        if not create and not path.exists():
            raise ValueError(f"Reference does not exist: {path.name}")
        return path

    @staticmethod
    def _audio_file(path: Path) -> Path | None:
        return next((p for p in sorted(path.iterdir()) if p.suffix.lower() in AUDIO_EXTENSIONS), None)
