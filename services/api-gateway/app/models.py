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

    async def activate(self, name: str, target: str) -> dict:
        model = next((item for item in self.list() if item["name"] == ensure_name(name, "Model name")), None)
        if not model:
            raise ValueError(f"Model does not exist: {name}")
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
        data = {"active": name, "path": model["path"], "target": target}
        await self.events.publish("model.activated", data)
        return data

    async def status(self) -> dict:
        models = self.list()
        render_runtime = await json_request("GET", f"{self.settings.render_url}/internal/status")
        live_runtime = (
            await json_request("GET", f"{self.settings.live_url}/internal/status")
            if self.settings.live_enabled
            else self._disabled_runtime()
        )
        return {
            "render": self._active(render_runtime["active_model_path"], models),
            "live": self._active(live_runtime["active_model_path"], models) if self.settings.live_enabled else None,
            "models": models,
            "render_runtime": render_runtime,
            "live_runtime": live_runtime,
        }

    def _row(self, name: str, path: Path, kind: str, engine: str) -> dict:
        return {"name": name, "kind": kind, "engine": engine, "path": str(path), "ready": path.exists()}

    def _active(self, path: str, models: list[dict]) -> dict | None:
        return next((item for item in models if item["path"] == path), None)

    @staticmethod
    def _disabled_runtime() -> dict:
        return {
            "active_model_path": "",
            "ready": False,
            "engine": "disabled",
            "detail": "Live runtime is disabled.",
        }
