"""ספק ענן משני (fallback) — Meshy API. דורש MESHY_API_KEY."""
import base64
import time
from pathlib import Path
from typing import Callable

import httpx

from ...config import settings
from ...schemas import GenOptions
from .base import MeshProvider, ProviderError, RawMeshResult

API = "https://api.meshy.ai/openapi/v1"


class MeshyProvider(MeshProvider):
    name = "meshy"

    def __init__(self):
        self.key = settings.meshy_api_key
        if not self.key:
            raise ProviderError("חסר מפתח MESHY_API_KEY", retryable=False)
        self.headers = {"Authorization": f"Bearer {self.key}"}

    def generate(self, image_path: Path, out_dir: Path, opts: GenOptions,
                 on_progress: Callable[[int, str], None]) -> RawMeshResult:
        timeout = settings.cloud_timeout
        data_uri = "data:image/png;base64," + base64.b64encode(image_path.read_bytes()).decode()

        with httpx.Client(timeout=60) as client:
            on_progress(10, "יוצר משימה ב-Meshy…")
            resp = client.post(f"{API}/image-to-3d", headers=self.headers, json={
                "image_url": data_uri,
                "should_remesh": True,
                "should_texture": opts.texture,
                "target_polycount": opts.target_polycount,
            })
            if resp.status_code not in (200, 202):
                raise ProviderError(f"Meshy דחה את הבקשה ({resp.status_code}): {resp.text[:200]}")
            task_id = resp.json()["result"]

            started = time.monotonic()
            while True:
                if time.monotonic() - started > timeout:
                    raise ProviderError(f"Meshy לא סיים בתוך {timeout} שניות")
                time.sleep(4)
                st = client.get(f"{API}/image-to-3d/{task_id}", headers=self.headers).json()
                status = st["status"]
                pct = 15 + int(0.7 * st.get("progress", 0))
                on_progress(min(pct, 85), f"Meshy מעבד… ({st.get('progress', 0)}%)")
                if status == "SUCCEEDED":
                    break
                if status in ("FAILED", "CANCELED"):
                    raise ProviderError(f"משימת Meshy נכשלה: {st.get('task_error', status)}")

            on_progress(88, "מוריד את המודל…")
            model_url = st["model_urls"].get("glb")
            if not model_url:
                raise ProviderError("Meshy לא החזיר GLB")
            out = out_dir / "model_raw_meshy.glb"
            with client.stream("GET", model_url) as r:
                with open(out, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)

        return RawMeshResult(mesh_path=out, confidence=0.65, provider=self.name,
                             metadata={"task_id": task_id})
