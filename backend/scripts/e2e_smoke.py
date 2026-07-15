"""בדיקת קצה-לקצה (DoD של Phase 1): STL שבור → תיקון → סקייל → slicing → ZIP.

מריצים מול שרת חי:  python scripts/e2e_smoke.py [base_url]
"""
import io
import sys

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")  # קונסולת Windows cp1252
import time
import zipfile
from pathlib import Path

import httpx
import trimesh

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8008"
TIMEOUT = 180


def make_broken_stl() -> bytes:
    """קופסה עם חור + רכיב צף — בדיוק סוג הקלט שהצנרת חייבת להציל."""
    box = trimesh.creation.box(extents=[30, 20, 15])
    broken = trimesh.Trimesh(vertices=box.vertices.copy(), faces=box.faces[2:].copy(),
                             process=False)
    floater = trimesh.creation.box(extents=[0.4, 0.4, 0.4])
    floater.apply_translation([50, 50, 50])
    combined = trimesh.util.concatenate([broken, floater])
    assert not combined.is_watertight
    buf = io.BytesIO()
    combined.export(buf, file_type="stl")
    return buf.getvalue()


def wait_for_status(client: httpx.Client, job_id: str, target: str) -> dict:
    start = time.monotonic()
    while time.monotonic() - start < TIMEOUT:
        job = client.get(f"{BASE}/api/v1/jobs/{job_id}").json()
        if job["status"] == target:
            return job
        if job["status"] == "failed":
            raise SystemExit(f"FAIL: job failed — {job['error_he']}")
        time.sleep(1.5)
    raise SystemExit(f"FAIL: timeout waiting for {target} (last: {job['status']})")


def main():
    client = httpx.Client(timeout=30)

    health = client.get(f"{BASE}/api/v1/health").json()
    print(f"health: {health}")
    assert health["slicer_found"], "PrusaSlicer לא נמצא"

    profiles = client.get(f"{BASE}/api/v1/profiles").json()
    assert len(profiles) >= 6, f"רק {len(profiles)} פרופילים"
    mk4 = next(p for p in profiles if "MK4" in p["name"])
    print(f"profiles: {len(profiles)} (using {mk4['name']})")

    print("1. uploading broken STL…")
    stl = make_broken_stl()
    r = client.post(f"{BASE}/api/v1/jobs",
                    files=[("files", ("broken_box.stl", stl, "model/stl"))])
    assert r.status_code == 201, r.text
    job_id = r.json()["id"]
    print(f"   job: {job_id}")

    print("2. waiting for repair (awaiting_scale)…")
    job = wait_for_status(client, job_id, "awaiting_scale")
    qg3 = job["gates_json"].get("QG3", {})
    assert qg3.get("status") == "pass", f"QG3: {qg3}"
    print(f"   QG3: {qg3['message_he']}")

    print("3. setting scale (height 50mm, auto-orient)…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/scale",
                    json={"axis": "z", "size_mm": 50, "auto_orient": True})
    assert r.status_code == 200, r.text
    job = wait_for_status(client, job_id, "awaiting_slice")
    print(f"   dims: {next(s for s in job['stages'] if s['stage_name']=='scale_orient')['metrics_json'].get('dims_mm')}")

    print("4. slicing (MK4, standard, PLA)…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/slice",
                    json={"profile_id": mk4["id"], "preset": "standard", "material": "PLA"})
    assert r.status_code == 200, r.text
    job = wait_for_status(client, job_id, "done")
    stats = job["print_stats_json"]
    print(f"   time: {stats['time_s']}s · filament: {stats['filament_g']}g · "
          f"layers: {stats['layers']} · cost: ₪{stats['cost']['total_ils']}")
    assert stats["time_s"] > 0 and stats["filament_g"] > 0

    print("5. downloading ZIP…")
    r = client.get(f"{BASE}/api/v1/jobs/{job_id}/download")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    print(f"   zip contains: {names}")
    for expected in ("model/model_repaired.stl", "report/print_report.html",
                     "report/pipeline_metadata.json", "print/slicer_config_used.ini"):
        assert expected in names, f"חסר בחבילה: {expected}"
    assert any(n.startswith("print/") and n.endswith(".gcode") for n in names), "אין G-code"

    print("\n✅ E2E PASSED — broken STL became a validated print package")


if __name__ == "__main__":
    main()
