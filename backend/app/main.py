"""Photo2Print API — FastAPI + WebSocket progress."""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .jobqueue import progress_bus
from .routers import artifacts, jobs, profiles
from .seed import seed_profiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_profiles()
    progress_bus.attach_loop(asyncio.get_running_loop())
    yield


app = FastAPI(title="Photo2Print API", version="1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(profiles.router)
app.include_router(artifacts.router)


@app.get("/api/v1/health")
def health():
    from .config import settings
    slicer = settings.find_slicer()
    return {
        "status": "ok",
        "slicer_found": slicer is not None,
        "slicer_path": str(slicer) if slicer else None,
        "mesh_provider": settings.mesh_provider,
    }


@app.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(ws: WebSocket, job_id: str):
    """עדכוני התקדמות חיים לפי חוזה PRD §6.3."""
    await ws.accept()
    queue = progress_bus.subscribe(job_id)
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_json(event)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "keepalive", "job_id": job_id})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        progress_bus.unsubscribe(job_id, queue)
