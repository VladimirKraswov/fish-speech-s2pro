import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, events, path: Path, load_existing: bool = False) -> None:
        self.events = events
        self.path = path
        self.rows: dict[str, dict] = {}
        self.order = deque(maxlen=300)
        if load_existing:
            self._load()

    def create(self, kind: str, payload: dict, status: str = "queued") -> dict:
        now = self._now()
        job = {
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "status": status,
            "payload": payload,
            "result": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self.rows[job["id"]] = job
        self.order.appendleft(job["id"])
        self._store(job)
        self._emit("job.created", {"job": job})
        return job

    def update(self, job_id: str, status: str, result=None, error=None) -> dict:
        job = self.get(job_id)
        job["status"], job["result"], job["error"], job["updated_at"] = status, result, error, self._now()
        if job_id in self.order:
            self.order.remove(job_id)
        self.order.appendleft(job_id)
        self._store(job)
        self._emit("job.updated", {"job": job})
        return job

    def cancel(self, job_id: str, error: str = "Cancelled by user") -> dict:
        return self.update(job_id, "cancelled", self.get(job_id).get("result"), error)

    def list(self) -> list[dict]:
        return [self.rows[job_id] for job_id in self.order if job_id in self.rows]

    def get(self, job_id: str) -> dict:
        if job_id not in self.rows:
            raise ValueError(f"Job does not exist: {job_id}")
        return self.rows[job_id]

    def _load(self) -> None:
        if not self.path.exists():
            return
        order: list[str] = []
        for lineno, line in enumerate(
            self.path.read_text(encoding="utf-8", errors="replace").splitlines(),
            start=1,
        ):
            if not line.strip():
                continue
            try:
                job = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed job row in %s at line %s", self.path, lineno)
                continue
            job_id = job.get("id")
            if not job_id:
                logger.warning("Skipping job row without id in %s at line %s", self.path, lineno)
                continue
            self.rows[job_id] = job
            if job_id in order:
                order.remove(job_id)
            order.append(job_id)
        for job_id in order[-300:]:
            self.order.appendleft(job_id)

    def _store(self, job: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(job, ensure_ascii=False) + "\n")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _emit(self, kind: str, payload: dict) -> None:
        try:
            asyncio.get_running_loop().create_task(self.events.publish(kind, payload))
        except RuntimeError:
            pass
