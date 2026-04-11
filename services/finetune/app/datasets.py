from __future__ import annotations

from pathlib import Path

from shared.filesystem import ensure_name, pair_stats, sample_rows


class DatasetService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[dict]:
        return [self._summary(path) for path in sorted(self.root.iterdir()) if path.is_dir()]

    def _summary(self, path: Path) -> dict:
        return {"name": path.name, "path": str(path), **pair_stats(path), "samples": sample_rows(path)}

    def get(self, name: str) -> dict:
        path = self.root / ensure_name(name, "Dataset name")
        if not path.exists():
            raise ValueError(f"Dataset does not exist: {path.name}")
        return self._summary(path)
