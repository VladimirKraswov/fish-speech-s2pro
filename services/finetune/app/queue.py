import asyncio


class QueueService:
    def __init__(self, jobs) -> None:
        self.jobs = jobs
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.runners: dict[str, tuple] = {}
        self.cancelled: set[str] = set()
        self.active: str | None = None
        self.active_cancel = None
        self.worker: asyncio.Task | None = None

    async def startup(self) -> None:
        if self.worker and not self.worker.done():
            return
        self.worker = asyncio.create_task(self._work())

    async def shutdown(self) -> None:
        if self.active:
            if self.active_cancel:
                self.active_cancel()
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)

    def submit(self, job_id: str, run, cancel=None) -> None:
        if job_id in self.runners:
            raise ValueError(f"Job is already queued: {job_id}")
        self.runners[job_id] = (run, cancel)
        self.queue.put_nowait(job_id)

    def cancel(self, job_id: str) -> dict:
        if self.active == job_id:
            if self.active_cancel:
                self.active_cancel()
            return self.jobs.cancel(job_id, "Cancellation requested")
        self.cancelled.add(job_id)
        return self.jobs.cancel(job_id)

    async def _work(self) -> None:
        while True:
            job_id = await self.queue.get()
            if job_id in self.cancelled:
                self.cancelled.discard(job_id)
                continue
            run, _ = self.runners.pop(job_id, (None, None))
            if run is None:
                continue
            self.active = job_id
            self.active_cancel = _  # type: ignore[assignment]
            try:
                await run()
            except Exception as exc:
                self.jobs.update(job_id, "failed", self.jobs.get(job_id).get("result"), str(exc))
            finally:
                self.active = None
                self.active_cancel = None
