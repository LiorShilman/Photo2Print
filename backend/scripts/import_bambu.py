"""ייבוא פרופיל המדפסת המוגדרת מ-Bambu Studio אל Photo2Print.

קורא את הקונפיג המקומי של Bambu Studio, פותר את שרשרת הירושה של פרופיל
המערכת, ורושם פרופיל מדפסת דרך ה-API.

הרצה:  python scripts/import_bambu.py [machine_name] [base_url]
"""
import json
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import httpx

BAMBU_DIR = Path(os.environ["APPDATA"]) / "BambuStudio"
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8008"


def selected_machine() -> str:
    raw = (BAMBU_DIR / "BambuStudio.conf").read_text(encoding="utf-8")
    conf = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    name = conf.get("presets", {}).get("machine", "")
    if not name:
        raise SystemExit("לא נמצאה מדפסת נבחרת ב-Bambu Studio")
    return name


def resolve_profile(name: str) -> dict:
    """מיזוג שרשרת הירושה: child גובר על parent."""
    search_dirs = [BAMBU_DIR / "system" / "BBL" / "machine"]
    search_dirs += list((BAMBU_DIR / "user").glob("*/machine"))

    def load(n: str) -> dict:
        for d in search_dirs:
            f = d / f"{n}.json"
            if f.is_file():
                return json.loads(f.read_text(encoding="utf-8"))
        raise SystemExit(f"פרופיל לא נמצא: {n}")

    merged: dict = {}
    chain = []
    current = name
    while current:
        node = load(current)
        chain.append(current)
        current = node.get("inherits", "")
        for k, v in node.items():
            merged.setdefault(k, v)  # child כבר בפנים — parent רק משלים
    print(f"שרשרת ירושה: {' ← '.join(chain)}")
    return merged


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else selected_machine()
    print(f"מייבא: {name}")
    p = resolve_profile(name)

    area = p.get("printable_area") or []
    xs = [float(pt.split("x")[0]) for pt in area]
    ys = [float(pt.split("x")[1]) for pt in area]
    bed_x, bed_y = (max(xs), max(ys)) if xs else (256.0, 256.0)
    bed_z = float(p.get("printable_height", 250))
    nozzle_list = p.get("nozzle_diameter") or ["0.4"]
    nozzle = float(nozzle_list[0] if isinstance(nozzle_list, list) else nozzle_list)

    print(f"משטח: {bed_x}×{bed_y}×{bed_z} מ\"מ · נחיר {nozzle}")

    profile_name = f"{name} (Bambu Studio)"
    r = httpx.post(f"{BASE}/api/v1/profiles", json={
        "name": profile_name, "vendor": "Bambu",
        "bed_x": bed_x, "bed_y": bed_y, "bed_z": bed_z,
        "nozzle_mm": nozzle, "slicer_ini_base": "generic_fdm.ini",
    }, timeout=15)
    if r.status_code == 201:
        print(f"✅ נוצר פרופיל: {profile_name}")
    elif r.status_code == 409:
        print(f"הפרופיל כבר קיים: {profile_name}")
    else:
        raise SystemExit(f"שגיאה: {r.status_code} {r.text}")


if __name__ == "__main__":
    main()
