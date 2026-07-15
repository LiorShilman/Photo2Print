"""תור עבודות in-process + ערוץ progress ל-WebSocket.

תחליף ל-Redis/RQ בפריסה מקומית (ADR-2 נשמר: ג'ובים אסינכרוניים,
HTTP לא נחסם, עדכוני התקדמות בזמן אמת). המבנה מאפשר החלפה עתידית
ב-Redis בלי לשנות את הצנרת.
"""
import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger("p2p.queue")

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="p2p-worker")


class ProgressBus:
    """pub/sub פנימי: worker threads מפרסמים, WebSocket clients מאזינים."""

    def __init__(self):
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._last_event: dict[str, dict] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def publish(self, job_id: str, event: dict[str, Any]):
        """נקרא מ-worker thread. דוחף לכל המנויים דרך ה-event loop."""
        with self._lock:
            self._last_event[job_id] = event
            queues = list(self._subscribers.get(job_id, []))
        if self._loop is None or self._loop.is_closed():
            return
        for q in queues:
            try:
                self._loop.call_soon_threadsafe(q.put_nowait, event)
            except RuntimeError:
                pass

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
            last = self._last_event.get(job_id)
        if last is not None:
            q.put_nowait(last)
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)
            if not subs:
                self._subscribers.pop(job_id, None)


progress_bus = ProgressBus()


def enqueue(fn: Callable, *args, **kwargs):
    """הרצת שלב pipeline ברקע. חריגות מטופלות בתוך ה-runner עצמו."""
    def _wrapped():
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Unhandled pipeline error in %s", getattr(fn, "__name__", fn))
    return _executor.submit(_wrapped)
