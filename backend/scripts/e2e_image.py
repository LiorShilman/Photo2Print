"""בדיקת קצה-לקצה למסלול תמונה (UC-1): תמונה → rembg → mesh → G-code → ZIP.

רץ עם ספק local_extrude (ללא מפתח API). מייצר תמונת מבחן סינתטית:
צורת "בית" כהה וחדה על רקע בהיר — אידאלית להסרת רקע וחילוץ צללית.

הרצה:  python scripts/e2e_image.py [base_url]
"""
import io
import sys
import time
import zipfile

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8008"
TIMEOUT = 240


def make_test_image() -> bytes:
    """חפץ כהה מטוקסטר על רקע בהיר, 800×800 — עובר את ספי QG1."""
    im = Image.new("RGB", (800, 800), (235, 233, 228))
    draw = ImageDraw.Draw(im)
    # גוף "בית": ריבוע + גג משולש
    rng = np.random.default_rng(7)
    draw.polygon([(250, 350), (550, 350), (550, 620), (250, 620)], fill=(60, 55, 75))
    draw.polygon([(220, 360), (400, 190), (580, 360)], fill=(80, 45, 50))
    # טקסטורה (חדות): רעש נקודתי על האובייקט
    px = im.load()
    for _ in range(14000):
        x, y = int(rng.integers(220, 580)), int(rng.integers(190, 620))
        r, g, b = px[x, y]
        if r < 150:  # רק על האובייקט הכהה
            n = int(rng.integers(-38, 38))
            px[x, y] = (max(0, min(255, r + n)), max(0, min(255, g + n)), max(0, min(255, b + n)))
    # חלון בהיר — פרט פנימי
    draw.rectangle([320, 400, 390, 470], fill=(200, 190, 150))
    im = im.filter(ImageFilter.GaussianBlur(0.4))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def wait_for_status(client: httpx.Client, job_id: str, target: str) -> dict:
    start = time.monotonic()
    job = {}
    while time.monotonic() - start < TIMEOUT:
        job = client.get(f"{BASE}/api/v1/jobs/{job_id}").json()
        if job["status"] == target:
            return job
        if job["status"] == "failed":
            raise SystemExit(f"FAIL: job failed — {job['error_he']}")
        time.sleep(2)
    raise SystemExit(f"FAIL: timeout waiting for {target} (last: {job.get('status')})")


def main():
    client = httpx.Client(timeout=60)

    health = client.get(f"{BASE}/api/v1/health").json()
    print(f"health: {health}")

    profiles = client.get(f"{BASE}/api/v1/profiles").json()
    ender = next(p for p in profiles if "Ender" in p["name"])

    print("1. uploading synthetic photo…")
    r = client.post(f"{BASE}/api/v1/jobs",
                    files=[("files", ("house.png", make_test_image(), "image/png"))])
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    print(f"   job: {job_id}")

    print("2. preprocess + mesh generation (rembg עשוי להוריד מודל בהרצה ראשונה)…")
    job = wait_for_status(client, job_id, "awaiting_scale")
    print(f"   image_score: {job['image_score']} · QG1: {job['gates_json'].get('QG1', {}).get('status')}")
    print(f"   provider: {job['source_provider']} · confidence: {job['ai_confidence']}")
    qg3 = job["gates_json"].get("QG3", {})
    assert qg3.get("status") == "pass", f"QG3: {qg3}"
    print(f"   QG3: {qg3['message_he']}")

    print("3. scale to 60mm height…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/scale",
                    json={"axis": "z", "size_mm": 60, "auto_orient": True})
    assert r.status_code == 200, r.text
    job = wait_for_status(client, job_id, "awaiting_slice")

    print("4. slicing (Ender 3 V3, draft, PLA)…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/slice",
                    json={"profile_id": ender["id"], "preset": "draft", "material": "PLA"})
    assert r.status_code == 200, r.text
    job = wait_for_status(client, job_id, "done")
    stats = job["print_stats_json"]
    print(f"   time: {stats['time_s']}s · filament: {stats['filament_g']}g · layers: {stats['layers']}")
    assert stats["time_s"] > 0 and stats["filament_g"] > 0

    print("5. verifying ZIP…")
    r = client.get(f"{BASE}/api/v1/jobs/{job_id}/download")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert "model/model_repaired.stl" in names
    assert any(n.endswith(".gcode") for n in names)
    print(f"   {len(names)} files in package")

    print("\n✅ IMAGE E2E PASSED — photo became a validated print package (UC-1)")


if __name__ == "__main__":
    main()
