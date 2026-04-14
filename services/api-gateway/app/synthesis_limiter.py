from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class QueueTicket:
    wait_seconds: float
    queued_before_start: int
    running_at_start: int


class QueueFullError(RuntimeError):
    pass


class SynthesisLimiter:
    def __init__(self, max_concurrency: int, max_queue: int) -> None:
        self.max_concurrency = max(max_concurrency, 1)
        self.max_queue = max(max_queue, 0)
        self._active = 0
        self._waiters: deque[tuple[asyncio.Future[QueueTicket], float]] = deque()
        self._lock = asyncio.Lock()

    async def acquire(self) -> QueueTicket:
        loop = asyncio.get_running_loop()
        async with self._lock:
            if self._active < self.max_concurrency and not self._waiters:
                self._active += 1
                return QueueTicket(wait_seconds=0.0, queued_before_start=0, running_at_start=self._active)

            if len(self._waiters) >= self.max_queue:
                raise QueueFullError(
                    "Render synthesis queue is full. "
                    f"running={self._active}, queued={len(self._waiters)}, "
                    f"max_concurrency={self.max_concurrency}, max_queue={self.max_queue}"
                )

            enqueued_at = time.perf_counter()
            waiter: asyncio.Future[QueueTicket] = loop.create_future()
            self._waiters.append((waiter, enqueued_at))

        try:
            return await waiter
        except asyncio.CancelledError:
            async with self._lock:
                self._waiters = deque((future, ts) for future, ts in self._waiters if future is not waiter)
            raise

    async def release(self) -> None:
        async with self._lock:
            while self._waiters:
                waiter, enqueued_at = self._waiters.popleft()
                if waiter.cancelled():
                    continue
                queued_before_start = len(self._waiters)
                ticket = QueueTicket(
                    wait_seconds=max(time.perf_counter() - enqueued_at, 0.0),
                    queued_before_start=queued_before_start,
                    running_at_start=self._active,
                )
                waiter.set_result(ticket)
                return
            self._active = max(self._active - 1, 0)

    def snapshot(self) -> dict[str, int]:
        return {
            "running": self._active,
            "queued": len(self._waiters),
            "max_concurrency": self.max_concurrency,
            "max_queue": self.max_queue,
        }
