"""דמו מרשים — ממלא את הגלריה במודלים אסתטיים ומריץ אותם עד G-code.

מודלים: אגרטל מסתובב, רגלי שח (pawn), כוכב, גלגל שיניים — כולם נוצרים
פרוגרמטית ועוברים את כל הצנרת. הכוכב נפרס עם החלפות צבע (M600).

הרצה:  python scripts/demo_showcase.py [base_url]
"""
import io
import sys
import time

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
import numpy as np
import trimesh
from shapely.geometry import Polygon

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8008"
TIMEOUT = 300


# ---------- יצירת מודלים ----------

def make_vase() -> trimesh.Trimesh:
    """אגרטל בעל פרופיל גלי — revolve של עקומה חלקה."""
    t = np.linspace(0, 1, 60)
    radius = 16 + 7 * np.sin(t * np.pi * 2.2) * (0.4 + 0.6 * t) + 6 * t
    height = t * 70
    profile = np.column_stack([radius, height])
    profile = np.vstack([[0.01, 0], profile[0:1] * [1, 0] + [0, 0], profile, [[0.01, 70]]])
    vase = trimesh.creation.revolve(profile, sections=72)
    return vase


def make_pawn() -> trimesh.Trimesh:
    """רגלי שחמט — בסיס, גוף קעור, צווארון וראש כדורי."""
    t = np.linspace(0, 1, 80)
    r = np.piecewise(
        t,
        [t < 0.12, (t >= 0.12) & (t < 0.2), (t >= 0.2) & (t < 0.62),
         (t >= 0.62) & (t < 0.7), t >= 0.7],
        [lambda s: 14 - 18 * s,                                  # בסיס מתעגל
         lambda s: 11.8 - 30 * (s - 0.12),                       # שקע
         lambda s: 9.4 - 7.5 * np.sin((s - 0.2) / 0.42 * np.pi * 0.5),  # גוף קעור
         lambda s: 4 + 42 * (s - 0.62),                          # צווארון
         lambda s: np.sqrt(np.maximum(7.5**2 - ((s - 0.85) * 55)**2, 0.01))],  # ראש
    )
    profile = np.column_stack([np.maximum(r, 0.01), t * 55])
    profile = np.vstack([[0.01, 0], profile, [0.01, 55]])
    return trimesh.creation.revolve(profile, sections=64)


def make_star() -> trimesh.Trimesh:
    """כוכב 5 קצוות בעובי נעים — מועמד מושלם להחלפות צבע."""
    pts = []
    for i in range(10):
        ang = i * np.pi / 5 - np.pi / 2
        r = 30 if i % 2 == 0 else 12.5
        pts.append((r * np.cos(ang), r * np.sin(ang)))
    star = trimesh.creation.extrude_polygon(Polygon(pts).buffer(1.5), height=12)
    return star


def make_gear() -> trimesh.Trimesh:
    """גלגל שיניים עם חור מרכזי."""
    teeth, r_out, r_in = 14, 28, 22
    pts = []
    for i in range(teeth * 4):
        ang = i / (teeth * 4) * 2 * np.pi
        phase = (i % 4)
        r = r_out if phase in (1, 2) else r_in
        pts.append((r * np.cos(ang), r * np.sin(ang)))
    outer = Polygon(pts).buffer(0.8).simplify(0.3)
    hole = Polygon([(6 * np.cos(a), 6 * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 32)])
    return trimesh.creation.extrude_polygon(outer.difference(hole), height=10)


# ---------- הרצה דרך ה-API ----------

def wait_for(client, job_id, targets: set[str], budget=TIMEOUT) -> dict:
    start = time.monotonic()
    job = {}
    while time.monotonic() - start < budget:
        job = client.get(f"{BASE}/api/v1/jobs/{job_id}").json()
        if job["status"] in targets or job["status"] == "failed":
            return job
        time.sleep(1.5)
    raise SystemExit(f"timeout (last: {job.get('status')})")


def run_model(client, name: str, mesh: trimesh.Trimesh, profile_id: str,
              size_mm: float, axis: str = "z", preset: str = "standard",
              color_changes: list | None = None) -> str:
    buf = io.BytesIO()
    mesh.export(buf, file_type="stl")
    r = client.post(f"{BASE}/api/v1/jobs",
                    files=[("files", (f"{name}.stl", buf.getvalue(), "model/stl"))])
    job_id = r.json()["id"]
    print(f"  {name}: {job_id} …", end="", flush=True)

    job = wait_for(client, job_id, {"awaiting_scale"})
    if job["status"] == "failed":
        print(f" ✗ repair: {job['error_he']}")
        return job_id

    client.post(f"{BASE}/api/v1/jobs/{job_id}/scale",
                json={"axis": axis, "size_mm": size_mm, "auto_orient": False,
                      "profile_id": profile_id})
    job = wait_for(client, job_id, {"awaiting_slice"})
    if job["status"] == "failed":
        print(f" ✗ scale: {job['error_he']}")
        return job_id

    advanced = {"color_changes": color_changes} if color_changes else None
    client.post(f"{BASE}/api/v1/jobs/{job_id}/slice",
                json={"profile_id": profile_id, "preset": preset,
                      "material": "PLA", "advanced": advanced})
    job = wait_for(client, job_id, {"done"})
    if job["status"] == "failed":
        print(f" ✗ slice: {job['error_he']}")
    else:
        s = job["print_stats_json"]
        extra = f" · 🎨 {len(color_changes)} החלפות צבע" if color_changes else ""
        print(f" ✓ {s['layers']} שכבות · {s['filament_g']:.0f} גרם{extra}")
    return job_id


def main():
    client = httpx.Client(timeout=60)
    profiles = client.get(f"{BASE}/api/v1/profiles").json()
    bambu = next(p for p in profiles if "X1C" in p["name"])   # מדפסת עם יכולת צבע
    prusa = next(p for p in profiles if "MK4" in p["name"])

    print("יוצר מודלים ומריץ דרך הצנרת:")
    run_model(client, "vase", make_vase(), prusa["id"], 90, preset="draft")
    run_model(client, "chess_pawn", make_pawn(), prusa["id"], 60)
    # כוכב תלת-שכבתי: בסיס אינדיגו → אמצע ורוד → קצה ענבר
    run_model(client, "star", make_star(), bambu["id"], 12, preset="draft",
              color_changes=[{"layer": 21, "color": "#f472b6"},
                             {"layer": 41, "color": "#fbbf24"}])
    run_model(client, "gear", make_gear(), bambu["id"], 10, preset="draft")

    print("\n✅ DEMO READY — פתח את http://localhost:5183 לגלריה")


if __name__ == "__main__":
    main()
