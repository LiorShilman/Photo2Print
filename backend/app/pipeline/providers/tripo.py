"""ספק ענן ראשי — Tripo3D API (image-to-3D). דורש TRIPO_API_KEY."""
import time
from pathlib import Path
from typing import Callable

import httpx

from ...config import settings
from ...schemas import GenOptions
from .base import MeshProvider, ProviderError, RawMeshResult

API = "https://api.tripo3d.ai/v2/openapi"


class TripoProvider(MeshProvider):
    name = "tripo"

    def __init__(self):
        self.key = settings.tripo_api_key
        if not self.key:
            raise ProviderError("חסר מפתח TRIPO_API_KEY — הגדר ב-.env או עבור לספק local_extrude",
                                retryable=False)
        self.headers = {"Authorization": f"Bearer {self.key}"}

    def _submit_and_wait(self, client: httpx.Client, task_payload: dict, out_dir: Path, out_name: str,
                         on_progress: Callable[[int, str], None]) -> RawMeshResult:
        """משותף ל-image/text: יצירת משימה, polling עד סיום (F-3.6), הורדת התוצאה."""
        timeout = settings.cloud_timeout
        resp = client.post(f"{API}/task", headers=self.headers, json=task_payload)
        if resp.status_code != 200:
            raise ProviderError(f"יצירת משימה נכשלה ({resp.status_code}): {resp.text[:200]}")
        task_id = resp.json()["data"]["task_id"]

        started = time.monotonic()
        while True:
            if time.monotonic() - started > timeout:
                raise ProviderError(f"Tripo לא סיים בתוך {timeout} שניות")
            time.sleep(4)
            st = client.get(f"{API}/task/{task_id}", headers=self.headers).json()["data"]
            status = st["status"]
            pct = 15 + int(0.7 * st.get("progress", 0))
            on_progress(min(pct, 85), f"Tripo3D מעבד… ({st.get('progress', 0)}%)")
            if status == "success":
                break
            if status in ("failed", "cancelled", "banned"):
                raise ProviderError(f"משימת Tripo נכשלה: {status}")

        on_progress(88, "מוריד את המודל…")
        model_url = st["output"].get("pbr_model") or st["output"].get("model")
        if not model_url:
            raise ProviderError("Tripo לא החזיר קובץ מודל")
        out = out_dir / out_name
        with client.stream("GET", model_url) as r:
            with open(out, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)

        confidence = float(st["output"].get("confidence", 0.7))
        return RawMeshResult(mesh_path=out, confidence=confidence, provider=self.name,
                             metadata={"task_id": task_id})

    def generate(self, image_path: Path, out_dir: Path, opts: GenOptions,
                 on_progress: Callable[[int, str], None]) -> RawMeshResult:
        with httpx.Client(timeout=60) as client:
            on_progress(5, "מעלה תמונה ל-Tripo3D…")
            with open(image_path, "rb") as f:
                up = client.post(f"{API}/upload/sts", headers=self.headers,
                                 files={"file": (image_path.name, f, "image/png")})
            if up.status_code != 200:
                raise ProviderError(f"העלאה ל-Tripo נכשלה ({up.status_code}): {up.text[:200]}")
            image_token = up.json()["data"]["image_token"]

            on_progress(15, "יוצר משימת image-to-3D…")
            task_payload = {
                "type": "image_to_model",
                "file": {"type": "png", "file_token": image_token},
                "model_version": "v2.5-20250123",
                "texture": opts.texture,
                "pbr": False,
                "face_limit": opts.target_polycount,
            }
            return self._submit_and_wait(client, task_payload, out_dir, "model_raw_tripo.glb", on_progress)

    def generate_from_text(self, prompt: str, out_dir: Path, opts: GenOptions,
                           on_progress: Callable[[int, str], None]) -> RawMeshResult:
        with httpx.Client(timeout=60) as client:
            on_progress(10, "יוצר משימת טקסט-ל-3D…")
            task_payload = {
                "type": "text_to_model",
                "prompt": prompt,
                "model_version": "v2.5-20250123",
                "texture": opts.texture,
                "pbr": False,
                "face_limit": opts.target_polycount,
            }
            return self._submit_and_wait(client, task_payload, out_dir, "model_raw_tripo_text.glb", on_progress)
