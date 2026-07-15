"""בדיקת קצה-לקצה לחיתוך לחלקים: מודל גדול מהמשטח → כשל QG5 → split → G-code לכל חלק.

הרצה:  python scripts/e2e_split.py [base_url]
"""
import io
import sys
import time
import zipfile

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import trimesh

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8008"
TIMEOUT = 240


def wait_for(client, job_id, targets: set[str]) -> dict:
    start = time.monotonic()
    job = {}
    while time.monotonic() - start < TIMEOUT:
        job = client.get(f"{BASE}/api/v1/jobs/{job_id}").json()
        if job["status"] in targets:
            return job
        time.sleep(1.5)
    raise SystemExit(f"FAIL: timeout (last: {job.get('status')})")


def main():
    client = httpx.Client(timeout=30)
    profiles = client.get(f"{BASE}/api/v1/profiles").json()
    mk4 = next(p for p in profiles if "MK4" in p["name"])

    print("1. uploading long bar STL…")
    bar = trimesh.creation.box(extents=[100, 20, 20])
    buf = io.BytesIO()
    bar.export(buf, file_type="stl")
    r = client.post(f"{BASE}/api/v1/jobs", files=[("files", ("bar.stl", buf.getvalue(), "model/stl"))])
    job_id = r.json()["id"]
    job = wait_for(client, job_id, {"awaiting_scale"})
    print(f"   job: {job_id}")

    print("2. scaling to 500mm width — should FAIL on QG5 (bed 250mm)…")
    client.post(f"{BASE}/api/v1/jobs/{job_id}/scale",
                json={"axis": "x", "size_mm": 500, "auto_orient": False, "profile_id": mk4["id"]})
    # profile חובה על הג'וב כדי ש-QG5 ירוץ — נקבע דרך duplicate? לא: scale משתמש ב-job.profile_id
    job = wait_for(client, job_id, {"failed", "awaiting_slice"})
    if job["status"] == "awaiting_slice":
        raise SystemExit("FAIL: expected QG5 failure for oversized model")
    gate = (job["stages"][-1].get("error_json") or {}).get("gate")
    assert gate == "QG5", f"expected QG5, got {gate}: {job['error_he']}"
    print(f"   ✓ failed on QG5 as expected: {job['error_he']}")

    print("3. re-scaling with allow_split=true…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/scale",
                    json={"axis": "x", "size_mm": 500, "auto_orient": False, "allow_split": True})
    assert r.status_code == 200, r.text
    job = wait_for(client, job_id, {"awaiting_slice", "failed"})
    assert job["status"] == "awaiting_slice", f"split failed: {job['error_he']}"
    qg5 = job["gates_json"]["QG5"]
    print(f"   QG5: [{qg5['status']}] {qg5['message_he']}")
    assert qg5.get("parts", 0) >= 2

    print("4. slicing all parts…")
    r = client.post(f"{BASE}/api/v1/jobs/{job_id}/slice",
                    json={"profile_id": mk4["id"], "preset": "draft", "material": "PLA"})
    assert r.status_code == 200, r.text
    job = wait_for(client, job_id, {"done", "failed"})
    assert job["status"] == "done", f"slice failed: {job['error_he']}"
    stats = job["print_stats_json"]
    print(f"   parts: {len(stats['parts'])} · total {stats['time_s']}s · {stats['filament_g']:.0f}g")
    assert stats["parts"] and len(stats["parts"]) >= 2

    print("5. verifying ZIP contains all part gcodes…")
    r = client.get(f"{BASE}/api/v1/jobs/{job_id}/download")
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    gcodes = [n for n in names if n.endswith(".gcode")]
    print(f"   gcodes in zip: {gcodes}")
    assert len(gcodes) == len(stats["parts"])

    print("\n✅ SPLIT E2E PASSED — oversized model split, sliced per part, packaged")


if __name__ == "__main__":
    main()
