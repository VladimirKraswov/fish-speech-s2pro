from __future__ import annotations

from pathlib import Path
import shutil

from shared.filesystem import AUDIO_EXTENSIONS, ensure_file_name, ensure_name, save_upload


class ReferenceService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        return [self.get(path.name) for path in sorted(self.root.iterdir()) if path.is_dir()]

    def get(self, name: str) -> dict:
        path = self._dir(name)
        audio = next((p for p in sorted(path.iterdir()) if p.suffix.lower() in AUDIO_EXTENSIONS), None)
        lab = path / "sample.lab"
        return {"name": path.name, "path": str(path), "audio_file": audio.name if audio else None, "transcript": lab.read_text(encoding="utf-8", errors="replace") if lab.exists() else ""}

    def save(self, name: str, audio, transcript: str, replace: bool) -> dict:
        path = self._dir(name, create=True)
        transcript_text = transcript.strip()
        if not transcript_text:
            raise ValueError("Reference transcript is required.")
        if not path.exists():
            path.mkdir(parents=True)
        audio_name = ensure_file_name(audio.filename, AUDIO_EXTENSIONS)
        audio_target = path / f"sample{Path(audio_name).suffix.lower()}"
        if path.exists() and any(path.iterdir()) and not replace:
            raise ValueError("Reference already exists. Enable replace or delete it first.")
        for existing in path.iterdir():
            if existing.is_file():
                existing.unlink()
        save_upload(audio, audio_target)
        (path / "sample.lab").write_text(transcript_text, encoding="utf-8")
        return self.get(name)

    def delete(self, name: str) -> dict:
        path = self._dir(name)
        data = self.get(name)
        shutil.rmtree(path)
        return {"deleted": True, "reference": data}

    def _dir(self, name: str, create: bool = False) -> Path:
        path = self.root / ensure_name(name, "Reference name")
        if not create and not path.exists():
            raise ValueError(f"Reference does not exist: {path.name}")
        return path
