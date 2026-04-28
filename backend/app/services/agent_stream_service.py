import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from threading import Lock
from uuid import uuid4


@dataclass
class AgentStreamState:
    stream_id: str
    project_id: str
    queue: Queue = field(default_factory=Queue)
    closed: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


class AgentStreamService:
    def __init__(self) -> None:
        self._streams: dict[str, AgentStreamState] = {}
        self._lock = Lock()

    def create_stream(self, project_id: str) -> AgentStreamState:
        state = AgentStreamState(stream_id=str(uuid4()), project_id=project_id)
        with self._lock:
            self._streams[state.stream_id] = state
        return state

    def get_stream(self, stream_id: str) -> AgentStreamState | None:
        with self._lock:
            return self._streams.get(stream_id)

    def publish(self, stream_id: str, event: str, data: dict) -> None:
        state = self.get_stream(stream_id)
        if state is None or state.closed:
            return
        state.queue.put({"event": event, "data": data})

    def finish(self, stream_id: str, event: str = "done", data: dict | None = None) -> None:
        state = self.get_stream(stream_id)
        if state is None or state.closed:
            return
        state.closed = True
        state.queue.put({"event": event, "data": data or {}})

    async def stream_events(self, stream_id: str):
        state = self.get_stream(stream_id)
        if state is None:
            yield self._format_event("run_error", {"message": "stream_not_found"})
            return

        yield self._format_event("connected", {"stream_id": stream_id, "project_id": state.project_id})
        while True:
            item = await asyncio.to_thread(self._wait_for_item, stream_id, 15.0)
            if item is None:
                yield ": keep-alive\n\n"
                continue

            yield self._format_event(item["event"], item["data"])
            if item["event"] in {"done", "run_error", "result"}:
                break

        self._cleanup(stream_id)

    def _wait_for_item(self, stream_id: str, timeout: float) -> dict | None:
        state = self.get_stream(stream_id)
        if state is None:
            return {"event": "run_error", "data": {"message": "stream_not_found"}}
        try:
            return state.queue.get(timeout=timeout)
        except Empty:
            return None

    def _cleanup(self, stream_id: str) -> None:
        with self._lock:
            self._streams.pop(stream_id, None)

    def _format_event(self, event: str, data: dict) -> str:
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event}\ndata: {payload}\n\n"


agent_stream_service = AgentStreamService()
