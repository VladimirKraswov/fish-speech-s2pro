import asyncio
import json
from collections import deque
from datetime import datetime, timezone


class EventService:
    def __init__(self, history_limit: int = 200) -> None:
        self._listeners: set[asyncio.Queue] = set()
        self._history = deque(maxlen=history_limit)

    def history(self) -> list[dict]:
        return list(self._history)

    async def publish(self, kind: str, payload: dict) -> dict:
        event = {"kind": kind, "payload": payload, "timestamp": datetime.now(timezone.utc).isoformat()}
        self._history.append(event)
        for queue in list(self._listeners):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                self._listeners.discard(queue)
        return event

    async def stream(self):
        queue = asyncio.Queue(maxsize=50)
        self._listeners.add(queue)
        try:
            yield self._encode("hello", {"history": self.history()})
            while True:
                event = await queue.get()
                yield self._encode(event["kind"], event)
        finally:
            self._listeners.discard(queue)

    def _encode(self, event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
