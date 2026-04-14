from __future__ import annotations
from pathlib import Path
import re
import shutil

from shared.filesystem import AUDIO_EXTENSIONS, ensure_file_name, ensure_name, save_upload
from .reference_audio import load_reference_meta, normalize_reference_audio, probe_duration, save_reference_meta


class ReferenceService:
    MAX_TRANSCRIPT_CHARS_PER_SECOND = 32
    MAX_TRANSCRIPT_WORDS_PER_SECOND = 5
    MIN_TRANSCRIPT_CHAR_LIMIT = 180
    MIN_TRANSCRIPT_WORD_LIMIT = 28

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
        transcript = lab.read_text(encoding="utf-8", errors="replace") if lab.exists() else ""
        if audio and "duration_sec" not in meta:
            duration = probe_duration(audio)
            if duration:
                meta["duration_sec"] = round(duration, 3)
        meta["transcript_validation"] = self._validate_transcript(transcript, meta.get("duration_sec"))
        return {
            "name": path.name,
            "path": str(path),
            "audio_file": audio.name if audio else None,
            "transcript": transcript,
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
        source_target = path / f"source{Path(audio_name).suffix.lower()}"
        output_target = path / "sample.wav"
        save_upload(audio, source_target)
        meta = normalize_reference_audio(
            source_target,
            output_target,
            max_seconds=self.max_seconds,
            sample_rate=self.sample_rate,
            channels=self.channels,
        )
        meta["source_file"] = source_target.name
        (path / "sample.lab").write_text(transcript_text, encoding="utf-8")
        meta["transcript_validation"] = self._validate_transcript(transcript_text, meta.get("duration_sec"))
        save_reference_meta(path, meta)
        return self.get(name)

    def update_transcript(self, name: str, transcript: str) -> dict:
        path = self._dir(name)
        transcript_text = str(transcript or "").strip()
        if not transcript_text:
            raise ValueError("Reference transcript is required.")
        (path / "sample.lab").write_text(transcript_text, encoding="utf-8")
        meta = load_reference_meta(path)
        if "duration_sec" not in meta:
            audio = self._audio_file(path)
            if audio:
                duration = probe_duration(audio)
                if duration:
                    meta["duration_sec"] = round(duration, 3)
        meta["transcript_validation"] = self._validate_transcript(transcript_text, meta.get("duration_sec"))
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
            if existing.is_file() and existing.name not in {"sample.lab", "reference.json", target.name} and not existing.name.startswith("source."):
                existing.unlink()
        final_target = path / "sample.wav"
        if final_target.exists() and final_target != target:
            final_target.unlink()
        target.replace(final_target)
        new_meta["audio_file"] = final_target.name
        source_audio = next((candidate for candidate in sorted(path.iterdir()) if candidate.is_file() and candidate.name.startswith("source.")), None)
        if source_audio is not None:
            new_meta["source_file"] = source_audio.name
        transcript = (path / "sample.lab").read_text(encoding="utf-8", errors="replace") if (path / "sample.lab").exists() else ""
        new_meta["transcript_validation"] = self._validate_transcript(transcript, new_meta.get("duration_sec"))
        save_reference_meta(path, new_meta)
        return self.get(name)

    def assert_synthesis_safe(self, name: str) -> dict:
        data = self.get(name)
        validation = (data.get("reference_meta") or {}).get("transcript_validation") or {}
        if validation.get("valid", True):
            return data
        detail = validation.get("message") or (
            "Reference transcript does not look compatible with the uploaded audio. "
            "Update the transcript so it matches the spoken reference exactly."
        )
        raise ValueError(detail)

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

    def _dir(self, name: str, create: bool = False) -> Path:
        path = self.root / ensure_name(name, "Reference name")
        if not create and not path.exists():
            raise ValueError(f"Reference does not exist: {path.name}")
        return path

    @staticmethod
    def _audio_file(path: Path) -> Path | None:
        sample = path / "sample.wav"
        if sample.exists():
            return sample
        return next((p for p in sorted(path.iterdir()) if p.suffix.lower() in AUDIO_EXTENSIONS), None)

    def _validate_transcript(self, transcript: str, duration_sec: float | None) -> dict:
        text = str(transcript or "").strip()
        chars = len(text)
        words = len(re.findall(r"\S+", text))
        result = {
            "valid": True,
            "message": "",
            "chars": chars,
            "words": words,
            "duration_sec": round(float(duration_sec), 3) if duration_sec else None,
            "max_chars": None,
            "max_words": None,
            "chars_per_second": None,
            "words_per_second": None,
        }
        if not text:
            result["valid"] = False
            result["message"] = "Reference transcript is empty. Add the exact spoken text from the reference audio."
            return result
        if not duration_sec or duration_sec <= 0:
            return result

        max_chars = max(self.MIN_TRANSCRIPT_CHAR_LIMIT, int(round(duration_sec * self.MAX_TRANSCRIPT_CHARS_PER_SECOND)))
        max_words = max(self.MIN_TRANSCRIPT_WORD_LIMIT, int(round(duration_sec * self.MAX_TRANSCRIPT_WORDS_PER_SECOND)))
        chars_per_second = round(chars / duration_sec, 2)
        words_per_second = round(words / duration_sec, 2)
        result["max_chars"] = max_chars
        result["max_words"] = max_words
        result["chars_per_second"] = chars_per_second
        result["words_per_second"] = words_per_second

        if chars > max_chars or words > max_words:
            result["valid"] = False
            result["message"] = (
                "Reference transcript is much longer than the uploaded audio. "
                f"Audio is {duration_sec:.2f}s, but transcript has {chars} chars / {words} words. "
                "Fish Speech may continue reading the reference transcript instead of only cloning the voice. "
                "Replace the transcript with the exact text spoken in the reference audio."
            )
        return result
