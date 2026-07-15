"""שלב 4 — תיקון Mesh דטרמיניסטי (PRD §5.4), כל צעד מתועד עם diff (F-4.1).

צעדים: נרמול → הסרת רכיבים צפים → סגירת חורים → תיקון נורמלים →
הסרת degenerate → decimation → אימות watertight (QG-3).
"""
import numpy as np

from ...storage import artifact_path, latest_artifact, save_artifact
from ..context import GateFailure, StageContext, set_gate

TARGET_FACES_MAX = 500_000
TARGET_FACES_MIN = 150_000


def _counts(m) -> tuple[int, int]:
    return len(m.vertices), len(m.faces)


def _step_diff(before: tuple[int, int], after: tuple[int, int]) -> dict:
    return {
        "vertices": {"before": before[0], "after": after[0], "diff": after[0] - before[0]},
        "faces": {"before": before[1], "after": after[1], "diff": after[1] - before[1]},
    }


def repair_mesh(mesh, on_progress=lambda pct, msg: None) -> tuple["trimesh.Trimesh", dict]:
    """ליבת התיקון — פונקציה טהורה הניתנת לבדיקת unit על fixtures."""
    import trimesh

    steps: dict[str, dict] = {}

    # 1. נרמול — mesh יחיד, איחוד vertices כפולים
    on_progress(10, "מנרמל את הרשת ומאחד נקודות כפולות…")
    before = _counts(mesh)
    mesh.merge_vertices(merge_tex=True, merge_norm=True)
    mesh.update_faces(mesh.unique_faces())
    steps["merge_vertices"] = _step_diff(before, _counts(mesh))

    # 2. הסרת רכיבים צפים — components < 1% מנפח/גודל הראשי
    on_progress(25, "מסיר רכיבים צפים (רעש AI)…")
    before = _counts(mesh)
    components = mesh.split(only_watertight=False)
    if len(components) > 1:
        sizes = np.array([len(c.faces) for c in components])
        main_size = sizes.max()
        keep = [c for c, s in zip(components, sizes) if s >= 0.01 * main_size]
        mesh = trimesh.util.concatenate(keep) if len(keep) > 1 else keep[0]
    steps["remove_floaters"] = {**_step_diff(before, _counts(mesh)),
                                "components_removed": int(len(components) - 1) if len(components) > 1 else 0}

    # 3. סגירת חורים
    on_progress(45, "סוגר חורים ברשת…")
    before = _counts(mesh)
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)
    steps["fill_holes"] = {**_step_diff(before, _counts(mesh)),
                           "watertight_after": bool(mesh.is_watertight)}

    # 4. תיקון נורמלים — עקבי כלפי חוץ
    on_progress(60, "מתקן כיווני נורמלים…")
    trimesh.repair.fix_normals(mesh)
    trimesh.repair.fix_winding(mesh)
    trimesh.repair.fix_inversion(mesh)
    steps["fix_normals"] = {"winding_consistent": bool(mesh.is_winding_consistent)}

    # 5. הסרת degenerate faces
    on_progress(70, "מסיר משולשים פגומים…")
    before = _counts(mesh)
    mesh.update_faces(mesh.nondegenerate_faces(height=1e-8))
    mesh.remove_unreferenced_vertices()
    steps["remove_degenerate"] = _step_diff(before, _counts(mesh))

    # אם ההסרה פתחה חורים — סגירה חוזרת
    if not mesh.is_watertight:
        trimesh.repair.fill_holes(mesh)

    # 6. Decimation חכם — רק אם חורג מהיעד (quadric edge collapse)
    on_progress(80, "מפשט את הרשת לצפיפות יעד…")
    before = _counts(mesh)
    if len(mesh.faces) > TARGET_FACES_MAX:
        try:
            mesh = mesh.simplify_quadric_decimation(face_count=TARGET_FACES_MIN)
            trimesh.repair.fix_normals(mesh)
            if not mesh.is_watertight:
                trimesh.repair.fill_holes(mesh)
        except Exception:
            pass  # decimation אופציונלי — עדיף mesh כבד מכשל
    steps["decimation"] = _step_diff(before, _counts(mesh))

    # 7. אימות סופי
    volume = float(mesh.volume) if mesh.is_watertight else 0.0
    steps["final_validation"] = {
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "euler_number": int(mesh.euler_number),
        "volume": round(volume, 3),
        "faces": len(mesh.faces),
    }
    return mesh, steps


def poisson_rebuild(mesh):
    """מצב 'Poisson אגרסיבי' (F-4.3) — קירוב voxel remesh שמציל מודלים בעייתיים."""
    pitch = float(max(mesh.extents) / 160.0)
    vox = mesh.voxelized(pitch)
    rebuilt = vox.marching_cubes
    rebuilt.merge_vertices()
    import trimesh
    trimesh.repair.fix_normals(rebuilt)
    return rebuilt


def run(ctx: StageContext) -> dict:
    import trimesh

    raw = latest_artifact(ctx.job_id, "mesh_raw")
    mesh = trimesh.load(str(artifact_path(raw)), force="mesh")

    mesh, steps = repair_mesh(mesh, ctx.progress)

    # QG-3: watertight חובה. אם נכשל — נסיון הצלה אגרסיבי לפני עצירה
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        ctx.progress(88, "המודל עדיין לא אטום — מנסה שחזור אגרסיבי…")
        try:
            mesh = poisson_rebuild(mesh)
            steps["aggressive_rebuild"] = {
                "applied": True,
                "is_watertight": bool(mesh.is_watertight),
                "faces": len(mesh.faces),
            }
        except Exception as e:
            steps["aggressive_rebuild"] = {"applied": False, "error": str(e)}

    if not mesh.is_watertight or mesh.volume <= 0:
        set_gate(ctx.job_id, "QG3", "fail", "המודל אינו אטום (watertight) גם לאחר תיקון")
        raise GateFailure(
            "QG3", "לא ניתן לאטום את המודל להדפסה",
            ["נסה תמונה אחרת בזווית ברורה יותר", "הפעל מצב Poisson אגרסיבי",
             "אם העלית קובץ — תקן אותו בתוכנת מידול"],
        )

    set_gate(ctx.job_id, "QG3", "pass",
             f"אטום ✓ | {len(mesh.faces):,} משולשים | נפח {mesh.volume:.1f} יח'³")

    out = ctx.work_dir / "model_repaired.stl"
    mesh.export(out)
    save_artifact(ctx.job_id, "mesh_repaired", out)

    ctx.progress(100, "התיקון הושלם — המודל אטום ותקין")
    return {"steps": steps}
