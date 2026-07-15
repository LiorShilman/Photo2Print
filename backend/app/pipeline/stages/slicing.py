"""שלב 7 — Slicing עם PrusaSlicer CLI (ADR-3: תהליך חיצוני מבודד).

בונה קובץ .ini דינמית (פרופיל בסיס + פריסט + חומר + Advanced), מריץ את
הסלייסר, מחלץ מטא-דאטה מה-G-code ואוכף QG-6.
"""
import re
import subprocess
from pathlib import Path

from ...config import PROJECT_ROOT, settings
from ...storage import artifact_path, latest_artifact, save_artifact
from ..context import GateFailure, StageContext, set_gate, set_job

PRESETS = {
    "draft":    {"layer_height": 0.28, "first_layer_height": 0.3, "perimeters": 2, "fill_density": "10%"},
    "standard": {"layer_height": 0.2,  "first_layer_height": 0.25, "perimeters": 2, "fill_density": "15%"},
    "quality":  {"layer_height": 0.12, "first_layer_height": 0.2, "perimeters": 3, "fill_density": "20%"},
}

MATERIALS = {
    "PLA":  {"temperature": 210, "first_layer_temperature": 215, "bed_temperature": 60,
             "first_layer_bed_temperature": 60, "filament_type": "PLA", "filament_density": 1.24},
    "PETG": {"temperature": 240, "first_layer_temperature": 245, "bed_temperature": 85,
             "first_layer_bed_temperature": 85, "filament_type": "PETG", "filament_density": 1.27},
    "TPU":  {"temperature": 225, "first_layer_temperature": 230, "bed_temperature": 45,
             "first_layer_bed_temperature": 45, "filament_type": "FLEX", "filament_density": 1.21},
}


def build_ini(base_ini_path: Path, preset: str, material: str, advanced: dict | None) -> str:
    """מיזוג שכבות קונפיג: בסיס-מדפסת ← פריסט ← חומר ← Advanced."""
    config: dict[str, str] = {}
    for line in base_ini_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        config[k.strip()] = v.strip()

    for k, v in PRESETS[preset].items():
        config[k] = str(v)
    for k, v in MATERIALS[material].items():
        config[k] = str(v)

    if advanced:
        mapping = {
            "layer_height": "layer_height",
            "perimeters": "perimeters",
            "nozzle_temp": "temperature",
            "bed_temp": "bed_temperature",
        }
        for src, dst in mapping.items():
            if advanced.get(src) is not None:
                config[dst] = str(advanced[src])
        if advanced.get("infill_pct") is not None:
            config["fill_density"] = f"{advanced['infill_pct']}%"
        if advanced.get("infill_pattern"):
            config["fill_pattern"] = advanced["infill_pattern"]
        if advanced.get("supports") is not None:
            sup = advanced["supports"]
            config["support_material"] = "1" if sup in ("auto", "tree") else "0"
            config["support_material_auto"] = "1" if sup in ("auto", "tree") else "0"
            config["support_material_style"] = "organic" if sup == "tree" else "grid"
        if advanced.get("brim") is not None:
            config["brim_width"] = "5" if advanced["brim"] else "0"
        if advanced.get("raft") is not None:
            config["raft_layers"] = "3" if advanced["raft"] else "0"

    return "\n".join(f"{k} = {v}" for k, v in sorted(config.items())) + "\n"


def parse_gcode_metadata(gcode_path: Path) -> dict:
    """חילוץ זמן/חוט/שכבות מהערות PrusaSlicer (F-7.5)."""
    meta = {"time_s": 0, "filament_mm": 0.0, "filament_g": 0.0, "layers": 0}
    xy_min = [float("inf")] * 2
    xy_max = [float("-inf")] * 2
    z_max = 0.0
    move_re = re.compile(r"^G[01]\b[^;]*")
    coord_re = re.compile(r"([XYZ])(-?\d+\.?\d*)")

    with open(gcode_path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.startswith(";"):
                if "estimated printing time" in line:
                    t = 0
                    for num, unit in re.findall(r"(\d+)\s*([dhms])", line):
                        t += int(num) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
                    meta["time_s"] = max(meta["time_s"], t)
                elif line.startswith("; filament used [mm]"):
                    meta["filament_mm"] = float(line.split("=")[1].split(",")[0])
                elif line.startswith("; filament used [g]"):
                    meta["filament_g"] = float(line.split("=")[1].split(",")[0])
                elif line.startswith(";LAYER_CHANGE"):
                    meta["layers"] += 1
                continue
            m = move_re.match(line)
            if m:
                for axis, val in coord_re.findall(m.group(0)):
                    v = float(val)
                    if axis == "X":
                        xy_min[0], xy_max[0] = min(xy_min[0], v), max(xy_max[0], v)
                    elif axis == "Y":
                        xy_min[1], xy_max[1] = min(xy_min[1], v), max(xy_max[1], v)
                    else:
                        z_max = max(z_max, v)

    meta["x_range"] = [xy_min[0], xy_max[0]] if xy_max[0] > xy_min[0] else None
    meta["y_range"] = [xy_min[1], xy_max[1]] if xy_max[1] > xy_min[1] else None
    meta["z_max"] = z_max
    return meta


def compute_cost(meta: dict) -> dict:
    """חישוב עלות (F-7.6): חוט + חשמל."""
    filament_cost = (meta["filament_g"] / 1000.0) * settings.filament_price_per_kg
    hours = meta["time_s"] / 3600.0
    electricity_cost = hours * (settings.printer_watts / 1000.0) * settings.electricity_price_per_kwh
    return {
        "filament_ils": round(filament_cost, 2),
        "electricity_ils": round(electricity_cost, 2),
        "total_ils": round(filament_cost + electricity_cost, 2),
    }


def run(ctx: StageContext) -> dict:
    from ...db import db_session
    from ...models import Job, PrinterProfile

    with db_session() as s:
        job = s.get(Job, ctx.job_id)
        slice_req = dict(job.slice_json or {})
        profile = s.get(PrinterProfile, slice_req.get("profile_id") or job.profile_id)

    if profile is None:
        raise GateFailure("QG6", "לא נבחר פרופיל מדפסת")

    slicer = settings.find_slicer()
    if slicer is None:
        raise GateFailure("QG6", "PrusaSlicer לא נמצא במערכת",
                          ["הרץ את סקריפט ההתקנה או הגדר P2P_SLICER_PATH ב-.env"])

    mesh_art = latest_artifact(ctx.job_id, "mesh_final") or latest_artifact(ctx.job_id, "mesh_repaired")
    mesh_path = artifact_path(mesh_art)

    preset = slice_req.get("preset", "standard")
    material = slice_req.get("material", "PLA")
    advanced = slice_req.get("advanced")

    ctx.progress(10, f"בונה קונפיגורציית {profile.name} · {preset} · {material}…")
    base_ini = PROJECT_ROOT / "backend" / "profiles" / profile.slicer_ini_base
    ini_text = build_ini(base_ini, preset, material, advanced)
    ini_path = ctx.work_dir / "slicer_config_used.ini"
    ini_path.write_text(ini_text, encoding="utf-8")

    safe_name = re.sub(r"[^\w\-]+", "_", profile.name.lower())
    gcode_path = ctx.work_dir / f"print_{safe_name}_{preset}.gcode"

    ctx.progress(25, "מריץ PrusaSlicer…")
    cmd = [str(slicer), "--export-gcode", "--load", str(ini_path),
           "--output", str(gcode_path), str(mesh_path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=settings.slice_timeout)
    except subprocess.TimeoutExpired:
        raise GateFailure("QG6", f"ה-Slicer לא סיים בתוך {settings.slice_timeout} שניות")

    if proc.returncode != 0 or not gcode_path.exists():
        err = (proc.stderr or proc.stdout or "").strip()[-500:]
        raise GateFailure("QG6", f"ה-Slicer נכשל: {err}",
                          ["בדוק שהמודל בתחום המשטח", "נסה פריסט אחר"])

    ctx.progress(70, "מחלץ מטא-דאטה מה-G-code…")
    meta = parse_gcode_metadata(gcode_path)
    cost = compute_cost(meta)

    # --- QG-6: G-code sanity ---
    problems = []
    if meta["time_s"] <= 0:
        problems.append("זמן הדפסה 0")
    if meta["filament_mm"] <= 0:
        problems.append("אין שימוש בחוט")
    margin = 1.0  # מ"מ סובלנות
    if meta["x_range"] and (meta["x_range"][0] < -margin or meta["x_range"][1] > profile.bed_x + margin):
        problems.append(f"תנועות X מחוץ לתחום ({meta['x_range']})")
    if meta["y_range"] and (meta["y_range"][0] < -margin or meta["y_range"][1] > profile.bed_y + margin):
        problems.append(f"תנועות Y מחוץ לתחום ({meta['y_range']})")
    if meta["z_max"] > profile.bed_z + margin:
        problems.append(f"גובה Z {meta['z_max']} חורג מ-{profile.bed_z}")

    if problems:
        set_gate(ctx.job_id, "QG6", "fail", " · ".join(problems))
        raise GateFailure("QG6", "ה-G-code לא עבר בדיקת תקינות: " + " · ".join(problems))

    set_gate(ctx.job_id, "QG6", "pass",
             f"{meta['layers']} שכבות · {meta['filament_g']:.0f} גרם · תקין")

    save_artifact(ctx.job_id, "gcode", gcode_path)
    save_artifact(ctx.job_id, "slicer_ini", ini_path)

    stats = {**meta, "cost": cost, "profile": profile.name, "preset": preset, "material": material}
    set_job(ctx.job_id, print_stats_json=stats, profile_id=profile.id)

    ctx.progress(100, "Slicing הושלם ואומת")
    return stats
