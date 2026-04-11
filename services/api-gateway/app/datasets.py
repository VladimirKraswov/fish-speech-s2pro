from __future__ import annotations

import shutil
from pathlib import Path

from shared.filesystem import AUDIO_EXTENSIONS, DATASET_EXTENSIONS, ensure_file_name, ensure_name, file_rows, pair_stats, sample_rows, save_upload


class DatasetService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        return [self._summary(path) for path in sorted(self.root.iterdir()) if path.is_dir()]

    def get(self, name: str) -> dict:
        return self._summary(self._dir(name), detailed=True)

    def create(self, name: str) -> dict:
        path = self._dir(name, create=True)
        if path.exists():
            raise ValueError(f"Dataset already exists: {path.name}")
        path.mkdir(parents=True, exist_ok=False)
        return self._summary(path, detailed=True)

    def delete(self, name: str) -> dict:
        path = self._dir(name)
        summary = self._summary(path)
        shutil.rmtree(path)
        return {"deleted": True, "dataset": summary}

    def upload_files(self, name: str, uploads: list, replace: bool) -> dict:
        path = self._dir(name)
        for upload in uploads:
            filename = ensure_file_name(upload.filename, DATASET_EXTENSIONS)
            target = path / filename
            if target.exists() and not replace:
                raise ValueError(f"File already exists: {filename}")
            save_upload(upload, target)
        return self.get(name)

    def save_sample(self, name: str, stem: str, audio, transcript: str, lab_file, replace: bool) -> dict:
        path = self._dir(name)
        stem = Path(ensure_name(stem, "Sample name")).stem
        audio_name = ensure_file_name(audio.filename, AUDIO_EXTENSIONS)
        audio_target = path / f"{stem}{Path(audio_name).suffix.lower()}"
        transcript_text = transcript.strip()
        has_lab_payload = lab_file is not None
        existing_lab = path / f"{stem}.lab"
        if not has_lab_payload and not transcript_text and not existing_lab.exists():
            raise ValueError("Provide transcript text or .lab file.")
        if audio_target.exists() and not replace:
            raise ValueError(f"Audio sample already exists: {audio_target.name}")
        for existing in path.glob(f"{stem}.*"):
            if replace and existing.suffix.lower() in DATASET_EXTENSIONS:
                existing.unlink()
        save_upload(audio, audio_target)
        lab_target = path / f"{stem}.lab"
        if has_lab_payload:
            save_upload(lab_file, lab_target)
        elif transcript_text:
            lab_target.write_text(transcript_text, encoding="utf-8")
        return self.get(name)

    def save_transcript(self, name: str, stem: str, transcript: str) -> dict:
        if not transcript.strip():
            raise ValueError("Transcript cannot be empty.")
        path = self._dir(name)
        (path / f"{Path(stem).stem}.lab").write_text(transcript.strip(), encoding="utf-8")
        return self.get(name)

    def delete_sample(self, name: str, stem: str) -> dict:
        path = self._dir(name)
        removed = False
        for target in path.glob(f"{Path(stem).stem}.*"):
            if target.suffix.lower() in DATASET_EXTENSIONS:
                target.unlink()
                removed = True
        if not removed:
            raise ValueError(f"Sample does not exist: {stem}")
        return self.get(name)

    def delete_file(self, name: str, filename: str) -> dict:
        target = self._dir(name) / ensure_file_name(filename, DATASET_EXTENSIONS)
        if not target.exists():
            raise ValueError(f"File does not exist: {filename}")
        target.unlink()
        return self.get(name)

    def _summary(self, path: Path, detailed: bool = False) -> dict:
        data = {"name": path.name, "path": str(path), **pair_stats(path)}
        if detailed:
            data["samples"] = sample_rows(path)
            data["files"] = file_rows(path)
        return data

    def _dir(self, name: str, create: bool = False) -> Path:
        path = self.root / ensure_name(name, "Dataset name")
        if not create and not path.exists():
            raise ValueError(f"Dataset does not exist: {path.name}")
        return path
