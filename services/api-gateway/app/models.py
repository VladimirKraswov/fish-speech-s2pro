from __future__ import annotations

from pathlib import Path

from shared.filesystem import ensure_name
from .remote import json_request


class ModelService:
    def __init__(self, settings, events) -> None:
        self.settings = settings
        self.events = events

    def list(self) -> list[dict]:
        rows = [self._row("s2-pro", self.settings.model_path, "base", "fish")]
        seen = {str(self.settings.model_path)}
        if self.settings.live_enabled and self.settings.live_engine == "s2cpp":
            rows.append(self._row(self.settings.live_model_path.stem, self.settings.live_model_path, "gguf", "s2cpp"))
        for path in sorted(self.settings.checkpoints_root.iterdir()):
            if path.is_dir() and str(path) not in seen:
                rows.append(self._row(path.name, path, "checkpoint", "fish"))
        for path in sorted(self.settings.checkpoints_root.rglob("*.gguf")):
            if str(path) not in seen and path != self.settings.live_model_path:
                rows.append(self._row(path.stem, path, "gguf", "s2cpp"))
        for path in sorted(self.settings.finetuned_root.iterdir()):
            if path.is_dir() and path.name not in {"results", "logs"}:
                rows.append(self._row(path.name, path, "lora", "fish"))
        return rows

    async def activate(self, name: str | None, target: str, path: str | None = None) -> dict:
        model = self._resolve_model(name=name, path=path, target=target)
        if target == "live" and not self.settings.live_enabled:
            raise RuntimeError("Live runtime is disabled.")

        url = self.settings.render_url if target == "render" else self.settings.live_url if target == "live" else None
        if not url:
            raise ValueError("Unknown model target")
        if target == "render" and model["engine"] != "fish":
            raise ValueError("Render target supports only Fish Speech checkpoints.")
        if target == "live" and self.settings.live_enabled and self.settings.live_engine == "s2cpp" and model["engine"] != "s2cpp":
            raise ValueError("Live target is configured for s2.cpp and accepts only GGUF models.")
        await json_request("POST", f"{url}/internal/activate", json={"path": model["path"]})
        data = {"active": model["name"], "path": model["path"], "target": target}
        await self.events.publish("model.activated", data)
        return data

    async def status(self) -> dict:
        models = self.list()
        render_runtime = await json_request("GET", f"{self.settings.render_url}/internal/status")
        render_engine = render_runtime.get("engine", "fish")
        live_runtime = (
            await json_request("GET", f"{self.settings.live_url}/internal/status")
            if self.settings.live_enabled
            else self._disabled_runtime()
        )
        render_active = self._active_or_external(render_runtime["active_model_path"], models, render_engine)
        if render_active:
            render_active = {**render_active, "engine": render_engine}
        live_active = self._active_or_external(live_runtime["active_model_path"], models, live_runtime.get("engine", "disabled")) if self.settings.live_enabled else None
        for active in (render_active, live_active):
            if active and all(item["path"] != active["path"] for item in models):
                models = [active, *models]
        return {
            "render": render_active,
            "live": live_active,
            "models": models,
            "render_runtime": render_runtime,
            "live_runtime": live_runtime,
        }

    def _row(self, name: str, path: Path, kind: str, engine: str) -> dict:
        return {"name": name, "kind": kind, "engine": engine, "path": str(path), "ready": path.exists()}

    def _active(self, path: str, models: list[dict]) -> dict | None:
        return next((item for item in models if item["path"] == path), None)

    def _active_or_external(self, path: str, models: list[dict], engine: str) -> dict | None:
        active = self._active(path, models)
        if active or not path:
            return active
        candidate = Path(path)
        kind = "external"
        if candidate.is_dir():
            engine_name = "fish"
            name = candidate.name
        else:
            engine_name = "s2cpp" if candidate.suffix.lower() == ".gguf" else engine
            name = candidate.stem or candidate.name
        return self._row(name, candidate, kind, engine_name)

    def _resolve_model(self, *, name: str | None, path: str | None, target: str) -> dict:
        if name and path:
            raise ValueError("Provide either model name or path, not both.")
        if path:
            return self._model_from_path(path, target)
        if not name:
            raise ValueError("Model name or path is required.")
        model = next((item for item in self.list() if item["name"] == ensure_name(name, "Model name")), None)
        if not model:
            raise ValueError(f"Model does not exist: {name}")
        return model

    def _model_from_path(self, path: str, target: str) -> dict:
        candidate = Path(str(path or "").strip())
        if not str(candidate):
            raise ValueError("Model path is required.")
        if target == "render":
            if not candidate.exists():
                raise ValueError(f"Render model path does not exist: {candidate}")
            if not candidate.is_dir():
                raise ValueError(f"Render model path must be a directory: {candidate}")
            codec_path = candidate / "codec.pth"
            if not codec_path.exists():
                raise ValueError(f"Render model is missing codec checkpoint: {codec_path}")
            return self._row(candidate.name, candidate, "external", "fish")
        if target == "live":
            if not candidate.exists():
                raise ValueError(f"Live model path does not exist: {candidate}")
            if candidate.suffix.lower() != ".gguf":
                raise ValueError("Live model path must point to a .gguf file for s2.cpp.")
            return self._row(candidate.stem, candidate, "external", "s2cpp")
        raise ValueError("Unknown model target")

    @staticmethod
    def _disabled_runtime() -> dict:
        return {
            "active_model_path": "",
            "ready": False,
            "engine": "disabled",
            "detail": "Live runtime is disabled.",
        }
