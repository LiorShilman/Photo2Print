"""שלב 8 — אריזה ופלט (PRD §5.8): ZIP + previews + דוח HTML עברי + metadata."""
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from ...storage import artifact_path, latest_artifact, save_artifact
from ..context import StageContext

VIEWS = {"iso": (28, 45), "front": (0, 0), "side": (0, 90), "top": (89, 0)}


def _hex_rgb(hex_color: str) -> "np.ndarray":
    h = hex_color.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)]) / 255.0


def render_previews(mesh_path: Path, out_dir: Path, on_progress,
                    zones: list[dict] | None = None) -> list[Path]:
    """רנדור סטטי headless עם matplotlib — עמיד יותר מ-GL בשרת ללא תצוגה."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import trimesh
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    mesh = trimesh.load(str(mesh_path), force="mesh")
    if len(mesh.faces) > 40_000:  # דגימה לרנדור מהיר
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=30_000)
        except Exception:
            pass

    tris = mesh.triangles
    # הצללה ידנית: בהירות לפי זווית הנורמל מול כיוון האור
    light = np.array([0.4, -0.6, 0.7])
    light = light / np.linalg.norm(light)
    intensity = 0.35 + 0.65 * np.clip(mesh.face_normals @ light, 0, 1)
    base = np.array([0x81, 0x8c, 0xf8]) / 255.0  # אינדיגו — תואם לפלטת ה-UI

    # צבע בסיס פר-פאה: אם יש אזורי M600 — לפי גובה מרכז הפאה
    face_base = np.tile(base, (len(tris), 1))
    if zones:
        centers_z = mesh.triangles_center[:, 2]
        for zone in sorted(zones, key=lambda s: s["z"]):
            face_base[centers_z >= zone["z"] - 1e-4] = _hex_rgb(zone["color"])
    face_colors = np.clip(intensity[:, None] * face_base, 0, 1)

    def _render(elev: float, azim: float, out: Path, size: float = 6, dpi: int = 100):
        fig = plt.figure(figsize=(size, size), facecolor="#131622")
        ax = fig.add_subplot(111, projection="3d", facecolor="#131622")
        coll = Poly3DCollection(tris, alpha=1.0)
        coll.set_facecolor(face_colors)
        ax.add_collection3d(coll)
        lo, hi = mesh.bounds
        # 0.62 — הפרויקציה התלת-ממדית של matplotlib מוסיפה שוליים משלה;
        # רדיוס הדוק ממלא את הפריים בלי לחתוך את המודל
        center, radius = (lo + hi) / 2, max(hi - lo) / 2 * 0.62
        for axis_set, c in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), center):
            axis_set(c - radius, c + radius)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        fig.savefig(out, dpi=dpi, bbox_inches="tight", facecolor="#131622")
        plt.close(fig)

    outputs = []
    for i, (name, (elev, azim)) in enumerate(VIEWS.items()):
        on_progress(15 + i * 8, f"מרנדר תצוגת {name}…")
        out = out_dir / f"views_{name}.png"
        _render(elev, azim, out)
        outputs.append(out)

    # turntable GIF — סיבוב 360° (PRD §5.8)
    on_progress(42, "מרנדר סיבוב 360°…")
    from PIL import Image as PILImage
    frames = []
    for k in range(18):
        frame_path = out_dir / f"_tt_{k}.png"
        _render(18, k * 20, frame_path, size=4, dpi=70)
        frames.append(PILImage.open(frame_path).convert("P", palette=PILImage.ADAPTIVE))
    gif_path = out_dir / "model_turntable.gif"
    frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                   duration=120, loop=0)
    for k in range(18):
        (out_dir / f"_tt_{k}.png").unlink(missing_ok=True)
    outputs.append(gif_path)
    return outputs


def build_report_html(job, stages, stats: dict, gates: dict) -> str:
    """דוח הדפסה עברי RTL כהה — self-contained."""
    from jinja2 import Template
    template = Template("""<!DOCTYPE html>
<html dir="rtl" lang="he"><head><meta charset="utf-8">
<title>דוח הדפסה — {{ job_id }}</title>
<style>
 body{background:#131622;color:#e4e7f1;font-family:'Segoe UI',Arial,sans-serif;max-width:860px;margin:2rem auto;padding:0 1rem}
 h1{color:#818cf8} h2{border-bottom:1px solid #2a3046;padding-bottom:.3rem;margin-top:2rem}
 table{width:100%;border-collapse:collapse;background:#1b1f2e;border-radius:8px}
 td,th{padding:.55rem .8rem;border-bottom:1px solid #262c3f;text-align:right}
 .pass{color:#3fb950}.warn{color:#f59e0b}.fail{color:#ef4444}
 .cards{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
 .card{background:#1b1f2e;border:1px solid #2a3046;border-radius:10px;padding:1rem 1.4rem;min-width:150px}
 .card b{display:block;font-size:1.5rem;color:#818cf8}
 .mono{font-family:'JetBrains Mono',Consolas,monospace;direction:ltr;display:inline-block}
</style></head><body>
<h1>🖨️ Photo2Print — דוח הדפסה</h1>
<p>ג'וב <span class="mono">{{ job_id }}</span> · נוצר {{ created }} · מקור: {{ provider }}</p>

<div class="cards">
 <div class="card"><b>{{ time_str }}</b>זמן הדפסה משוער</div>
 <div class="card"><b>{{ filament_g }} גרם</b>משקל חוט ({{ filament_m }} מ')</div>
 <div class="card"><b>₪{{ cost }}</b>עלות משוערת</div>
 <div class="card"><b>{{ layers }}</b>שכבות</div>
</div>

<h2>הגדרות הדפסה</h2>
<table>
 <tr><td>מדפסת</td><td>{{ printer }}</td></tr>
 <tr><td>פריסט</td><td>{{ preset }}</td></tr>
 <tr><td>חומר</td><td>{{ material }}</td></tr>
</table>

<h2>שערי איכות (Quality Gates)</h2>
<table><tr><th>שער</th><th>סטטוס</th><th>פירוט</th></tr>
{% for g, info in gates.items() %}
 <tr><td class="mono">{{ g }}</td>
     <td class="{{ info.status }}">{{ {'pass':'✔ עבר','warn':'⚠ אזהרה','fail':'✘ נכשל'}[info.status] }}</td>
     <td>{{ info.message_he }}</td></tr>
{% endfor %}
</table>

<h2>שלבי העיבוד</h2>
<table><tr><th>#</th><th>שלב</th><th>סטטוס</th><th>משך</th></tr>
{% for s in stages %}
 <tr><td>{{ s.idx }}</td><td>{{ s.name }}</td><td class="{{ 'pass' if s.status=='done' else 'fail' }}">{{ s.status }}</td><td class="mono">{{ s.duration }}</td></tr>
{% endfor %}
</table>
<p style="color:#96a0b8;margin-top:2rem">נוצר אוטומטית על ידי Photo2Print · מדיניות אפס-ניחושים: אף קובץ לא נארז בלי מעבר של כל השערים.</p>
</body></html>""")

    t = stats.get("time_s", 0)
    time_str = f"{t // 3600}:{(t % 3600) // 60:02d} שע'" if t >= 3600 else f"{t // 60} דק'"
    stage_rows = []
    for s in stages:
        dur = "-"
        if s.started_at and s.finished_at:
            dur = f"{(s.finished_at - s.started_at).total_seconds():.1f}s"
        stage_rows.append({"idx": s.stage_index, "name": s.stage_name, "status": s.status, "duration": dur})

    return template.render(
        job_id=job.id, created=job.created_at.strftime("%d/%m/%Y %H:%M"),
        provider=job.source_provider or "-",
        time_str=time_str,
        filament_g=round(stats.get("filament_g", 0), 1),
        filament_m=round(stats.get("filament_mm", 0) / 1000.0, 1),
        cost=stats.get("cost", {}).get("total_ils", 0),
        layers=stats.get("layers", 0),
        printer=stats.get("profile", "-"), preset=stats.get("preset", "-"),
        material=stats.get("material", "-"),
        gates=gates, stages=stage_rows,
    )


def run(ctx: StageContext) -> dict:
    from ...db import db_session
    from ...models import Job, JobStage

    with db_session() as s:
        job = s.get(Job, ctx.job_id)
        stages = (s.query(JobStage).filter_by(job_id=ctx.job_id)
                  .order_by(JobStage.stage_index).all())
        stats = dict(job.print_stats_json or {})
        gates = dict(job.gates_json or {})

    # אכיפת A-2: אסור לארוז עם gate אדום
    red = [g for g, info in gates.items() if info.get("status") == "fail"]
    if red:
        from ..context import GateFailure
        raise GateFailure(red[0], "לא ניתן לארוז — קיימים שערים אדומים: " + ", ".join(red))

    mesh_final = latest_artifact(ctx.job_id, "mesh_final") or latest_artifact(ctx.job_id, "mesh_repaired")

    # אזורי צבע (M600) — מיפוי שכבה→גובה Z לצביעת הרנדורים
    zones: list[dict] = []
    gcode_for_zones = latest_artifact(ctx.job_id, "gcode")
    if gcode_for_zones and stats.get("color_changes"):
        from ..gcode_preview import parse_layers
        try:
            layer_zs = [l["z"] for l in parse_layers(artifact_path(gcode_for_zones),
                                                     max_segments_per_layer=4)]
            for c in stats["color_changes"]:
                idx = min(max(int(c["layer"]) - 1, 0), len(layer_zs) - 1)
                zones.append({"z": layer_zs[idx], "color": c["color"]})
        except Exception:
            pass  # צביעה היא שיפור ויזואלי — לא מכשילה אריזה

    ctx.progress(10, "מרנדר תצוגות מקדימות…")
    previews = render_previews(artifact_path(mesh_final), ctx.work_dir, ctx.progress,
                               zones=zones or None)

    # שכבה ראשונה מה-G-code — קריטי לאבחון הצמדות (PRD §5.8)
    gcode_art = latest_artifact(ctx.job_id, "gcode")
    if gcode_art:
        ctx.progress(55, "מרנדר את השכבה הראשונה…")
        from ...models import PrinterProfile
        from ..gcode_preview import render_first_layer_png
        with db_session() as s:
            prof = s.get(PrinterProfile, job.profile_id) if job.profile_id else None
        bed = (prof.bed_x, prof.bed_y) if prof else (220.0, 220.0)
        fl_path = ctx.work_dir / "first_layer.png"
        try:
            if render_first_layer_png(artifact_path(gcode_art), fl_path, bed):
                previews.append(fl_path)
        except Exception:
            pass  # preview אופציונלי — לא מכשיל אריזה

    for p in previews:
        save_artifact(ctx.job_id, "preview", p)

    # ייצוא 3MF של המודל הסופי (PRD §5.8) — כולל הסקייל והאוריינטציה שהוחלו
    ctx.progress(60, "מייצא 3MF…")
    try:
        import trimesh
        m3 = trimesh.load(str(artifact_path(mesh_final)), force="mesh")
        p3mf = ctx.work_dir / "model_repaired.3mf"
        m3.export(p3mf)
        save_artifact(ctx.job_id, "mesh_3mf", p3mf)
    except Exception:
        pass  # 3MF משני ל-STL — לא מכשיל אריזה

    ctx.progress(65, "מפיק דוח הדפסה…")
    report_html = build_report_html(job, stages, stats, gates)
    report_path = ctx.work_dir / "print_report.html"
    report_path.write_text(report_html, encoding="utf-8")
    save_artifact(ctx.job_id, "report", report_path)

    metadata = {
        "job_id": job.id, "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_type": job.input_type, "provider": job.source_provider,
        "image_score": job.image_score, "ai_confidence": job.ai_confidence,
        "gates": gates, "print_stats": stats,
        "stages": [{"name": st.stage_name, "index": st.stage_index, "status": st.status,
                    "metrics": st.metrics_json} for st in stages],
    }
    meta_path = ctx.work_dir / "pipeline_metadata.json"
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    save_artifact(ctx.job_id, "report_json", meta_path)

    ctx.progress(80, "אורז ZIP…")
    zip_path = ctx.work_dir / f"photo2print_job_{job.id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        def _add(kind: str, arcname: str):
            art = latest_artifact(ctx.job_id, kind)
            if art:
                z.write(artifact_path(art), arcname)

        _add("mesh_final", "model/model_repaired.stl")
        _add("mesh_3mf", "model/model_repaired.3mf")
        _add("mesh_raw", "model/model_original_raw" + Path(latest_artifact(ctx.job_id, 'mesh_raw').filename).suffix)
        # כל קבצי ה-G-code (מודל שלם או ריבוי חלקים) — dedupe לפי שם, החדש גובר
        from ...models import Artifact
        with db_session() as s:
            gcode_arts = (s.query(Artifact).filter_by(job_id=ctx.job_id, kind="gcode")
                          .order_by(Artifact.created_at.asc(), Artifact.id.asc()).all())
        for art in {a.filename: a for a in gcode_arts}.values():
            z.write(artifact_path(art), f"print/{art.filename}")
        _add("slicer_ini", "print/slicer_config_used.ini")
        for p in previews:
            z.write(p, f"previews/{p.name}")
        z.write(report_path, "report/print_report.html")
        z.write(meta_path, "report/pipeline_metadata.json")

    save_artifact(ctx.job_id, "zip", zip_path)
    ctx.progress(100, "חבילת ההדפסה מוכנה")
    return {"zip_size_mb": round(zip_path.stat().st_size / (1024 * 1024), 2)}
