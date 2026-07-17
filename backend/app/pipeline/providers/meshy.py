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

    def _poll(self, client: httpx.Client, status_path: str, on_progress: Callable[[int, str], None],
              pct_base: int, pct_span: int, label: str) -> dict:
        timeout = settings.cloud_timeout
        started = time.monotonic()
        while True:
            if time.monotonic() - started > timeout:
                raise ProviderError(f"Meshy לא סיים בתוך {timeout} שניות")
            time.sleep(4)
            st = client.get(f"{API}/{status_path}", headers=self.headers).json()
            status = st["status"]
            pct = pct_base + int(pct_span * st.get("progress", 0) / 100)
            on_progress(min(pct, pct_base + pct_span), f"{label}… ({st.get('progress', 0)}%)")
            if status == "SUCCEEDED":
                return st
            if status in ("FAILED", "CANCELED"):
                raise ProviderError(f"משימת Meshy נכשלה: {st.get('task_error', status)}")

    def generate(self, image_path: Path, out_dir: Path, opts: GenOptions,
                 on_progress: Callable[[int, str], None]) -> RawMeshResult:
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

            st = self._poll(client, f"image-to-3d/{task_id}", on_progress, 15, 70, "Meshy מעבד")

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

    def generate_from_text(self, prompt: str, out_dir: Path, opts: GenOptions,
                           on_progress: Callable[[int, str], None]) -> RawMeshResult:
        """טקסט-ל-3D ב-Meshy הוא תהליך דו-שלבי: preview (גיאומטריה) ואז refine (עידון).

        מבוסס על תיעוד Meshy הידוע בזמן הכתיבה — מומלץ לוודא מול תיעוד עדכני
        אם ה-API משתנה, זו נקודת הסיכון היחידה בפאזה הזו.
        """
        with httpx.Client(timeout=60) as client:
            on_progress(5, "יוצר טיוטת גיאומטריה (preview)…")
            resp = client.post(f"{API}/text-to-3d", headers=self.headers, json={
                "mode": "preview", "prompt": prompt, "art_style": "realistic",
                "should_remesh": True, "target_polycount": opts.target_polycount,
            })
            if resp.status_code not in (200, 202):
                raise ProviderError(f"Meshy דחה את בקשת ה-preview ({resp.status_code}): {resp.text[:200]}")
            preview_id = resp.json()["result"]
            self._poll(client, f"text-to-3d/{preview_id}", on_progress, 10, 35, "בונה טיוטה")

            on_progress(45, "מעדן את המודל (refine)…")
            resp = client.post(f"{API}/text-to-3d", headers=self.headers, json={
                "mode": "refine", "preview_task_id": preview_id, "should_texture": opts.texture,
            })
            if resp.status_code not in (200, 202):
                raise ProviderError(f"Meshy דחה את בקשת ה-refine ({resp.status_code}): {resp.text[:200]}")
            refine_id = resp.json()["result"]
            st = self._poll(client, f"text-to-3d/{refine_id}", on_progress, 50, 38, "מעדן")

            on_progress(88, "מוריד את המודל…")
            model_url = st["model_urls"].get("glb")
            if not model_url:
                raise ProviderError("Meshy לא החזיר GLB")
            out = out_dir / "model_raw_meshy_text.glb"
            with client.stream("GET", model_url) as r:
                with open(out, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)

        return RawMeshResult(mesh_path=out, confidence=0.6, provider=self.name,
                             metadata={"preview_task_id": preview_id, "refine_task_id": refine_id})
