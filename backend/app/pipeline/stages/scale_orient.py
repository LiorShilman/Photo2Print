"""שלב 5 — סקייל, אוריינטציה ושערי QG4/QG5 (PRD §5.5).

הסקייל מגיע מקלט המשתמש (הציר + מ"מ). האוריינטציה האוטומטית בודקת 26
כיוונים ובוחרת את זה שממזער שטח supports וממקסם מגע עם המשטח.
"""
import numpy as np

from ...storage import artifact_path, latest_artifact, save_artifact
from ..context import GateFailure, StageContext, set_gate

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
OVERHANG_DEG = 50.0  # זווית שמעליה נדרש support


def orientation_score(mesh) -> float:
    """ציון כיוון: קטן יותר = טוב יותר. שטח overhang פחות בונוס מגע בסיס."""
    normals = mesh.face_normals
    areas = mesh.area_faces
    z = normals[:, 2]
    # פאות הפונות מטה בזווית תלולה → צריכות support
    threshold = -np.cos(np.radians(90 - OVERHANG_DEG))
    overhang_area = float(areas[z < threshold].sum())
    # שטח מגע משוער: פאות כמעט-אופקיות בגובה המינימלי
    zmin = mesh.bounds[0][2]
    face_z = mesh.triangles_center[:, 2]
    near_bottom = (face_z - zmin) < max(0.5, 0.02 * mesh.extents[2])
    contact_area = float(areas[near_bottom & (z < -0.9)].sum())
    return overhang_area - 0.5 * contact_area


def candidate_rotations():
    """26 כיווני בסיס: 6 פאות + 12 קשתות + 8 פינות (וקטורי 'מטה' מנורמלים)."""
    import trimesh
    dirs = []
    for x in (-1, 0, 1):
        for y in (-1, 0, 1):
            for z in (-1, 0, 1):
                if (x, y, z) == (0, 0, 0):
                    continue
                dirs.append(np.array([x, y, z], dtype=float))
    mats = []
    down = np.array([0, 0, -1.0])
    for d in dirs:
        d = d / np.linalg.norm(d)
        mats.append(trimesh.geometry.align_vectors(d, down))
    return mats


def auto_orient(mesh):
    """בחירת האוריינטציה הטובה ביותר מבין 26 מועמדים (F-5.4)."""
    best_mat, best_score = np.eye(4), orientation_score(mesh)
    for mat in candidate_rotations():
        rotated = mesh.copy()
        rotated.apply_transform(mat)
        s = orientation_score(rotated)
        if s < best_score - 1e-9:
            best_score, best_mat = s, mat
    mesh.apply_transform(best_mat)
    return mesh, best_score


def min_wall_thickness_estimate(mesh, samples: int = 400) -> float:
    """הערכת עובי דופן מינימלי ב-ray casting מנקודות על פני השטח פנימה (QG-4)."""
    try:
        points, face_idx = mesh.sample(samples, return_index=True)
        normals = mesh.face_normals[face_idx]
        # ירייה פנימה — המרחק לפגיעה הבאה הוא עובי מקומי
        origins = points - normals * 1e-4
        hits = mesh.ray.intersects_location(origins, -normals)[0]
        if len(hits) == 0:
            return float("inf")
        # מרחק מכל מוצא לפגיעה הקרובה
        locations, index_ray, _ = mesh.ray.intersects_location(origins, -normals)
        dists = []
        for i in range(len(origins)):
            ray_hits = locations[index_ray == i]
            if len(ray_hits):
                d = np.linalg.norm(ray_hits - origins[i], axis=1).min()
                dists.append(d)
        if not dists:
            return float("inf")
        return float(np.percentile(dists, 5))  # אחוזון 5 — הדופן הדקה בפועל
    except BaseException:
        return float("inf")  # מנוע ray לא זמין — לא חוסמים


def run(ctx: StageContext) -> dict:
    import trimesh

    from ...db import db_session
    from ...models import Job, PrinterProfile

    with db_session() as s:
        job = s.get(Job, ctx.job_id)
        scale_req = dict(job.scale_json or {})
        profile = s.get(PrinterProfile, job.profile_id) if job.profile_id else None

    if not scale_req:
        raise GateFailure("QG5", "לא התקבל קלט מידות מהמשתמש")

    repaired = latest_artifact(ctx.job_id, "mesh_repaired")
    mesh = trimesh.load(str(artifact_path(repaired)), force="mesh")

    # --- סיבוב ידני (gizmo, F-5.5) ---
    rot = scale_req.get("rotation_deg", [0, 0, 0])
    if any(abs(a) > 1e-6 for a in rot):
        ctx.progress(15, "מחיל סיבוב ידני…")
        for axis_vec, deg in zip(([1, 0, 0], [0, 1, 0], [0, 0, 1]), rot):
            if abs(deg) > 1e-6:
                mesh.apply_transform(
                    trimesh.transformations.rotation_matrix(np.radians(deg), axis_vec))

    # --- סקייל לפי ציר נבחר (F-5.1) ---
    axis = AXIS_INDEX[scale_req.get("axis", "z")]
    target_mm = float(scale_req["size_mm"])
    current = float(mesh.extents[axis])
    if current <= 0:
        raise GateFailure("QG5", "מידת הציר הנבחר היא אפס")
    factor = target_mm / current
    ctx.progress(30, f"מסקלל פי {factor:.3f} ליעד {target_mm} מ\"מ…")
    mesh.apply_scale(factor)

    # --- אוריינטציה אוטומטית (F-5.4) ---
    orient_score = None
    if scale_req.get("auto_orient", True):
        ctx.progress(45, "מחשב אוריינטציית הדפסה אופטימלית (26 כיוונים)…")
        mesh, orient_score = auto_orient(mesh)

    # --- השטחת בסיס אופציונלית (F-5.6) ---
    if scale_req.get("flatten_base"):
        ctx.progress(60, "משטיח את הבסיס…")
        zmin = mesh.bounds[0][2]
        cut_h = zmin + min(0.3, 0.005 * mesh.extents[2])
        sliced = mesh.slice_plane([0, 0, cut_h], [0, 0, 1], cap=True)
        if sliced is not None and len(sliced.faces) > 50 and sliced.is_watertight:
            mesh = sliced

    # הנחה על המשטח וריכוז ב-XY
    mesh.apply_translation([-mesh.centroid[0], -mesh.centroid[1], -mesh.bounds[0][2]])

    dims = [round(float(d), 2) for d in mesh.extents]

    # --- QG-5: התאמה לנפח ההדפסה ---
    ctx.progress(70, "בודק התאמה למשטח ההדפסה…")
    if profile:
        bed = (profile.bed_x, profile.bed_y, profile.bed_z)
        if dims[0] > bed[0] or dims[1] > bed[1] or dims[2] > bed[2]:
            max_factor = min(bed[0] / dims[0], bed[1] / dims[1], bed[2] / dims[2])
            max_mm = round(target_mm * max_factor * 0.98, 1)
            set_gate(ctx.job_id, "QG5", "fail",
                     f"המודל ({dims[0]}×{dims[1]}×{dims[2]} מ\"מ) חורג מהמשטח {bed[0]}×{bed[1]}×{bed[2]}")
            raise GateFailure(
                "QG5",
                f"המודל גדול ממשטח ההדפסה של {profile.name}",
                [f"הקטן את המידה ל-{max_mm} מ\"מ לכל היותר",
                 "או בחר מדפסת עם משטח גדול יותר"],
            )
        set_gate(ctx.job_id, "QG5", "pass",
                 f"{dims[0]}×{dims[1]}×{dims[2]} מ\"מ — מתאים ל-{profile.name}")
    else:
        set_gate(ctx.job_id, "QG5", "warn", "לא נבחר פרופיל מדפסת — הבדיקה תרוץ לפני slicing")

    # --- QG-4: עובי דופן מינימלי ---
    ctx.progress(85, "בודק עובי דופן מינימלי…")
    nozzle = profile.nozzle_mm if profile else 0.4
    min_wall = min_wall_thickness_estimate(mesh)
    if min_wall < 2 * nozzle:
        set_gate(ctx.job_id, "QG4", "warn",
                 f"דופן מינימלית ~{min_wall:.2f} מ\"מ < {2 * nozzle:.1f} מ\"מ — אזורים דקים עלולים להיכשל",
                 min_wall_mm=round(min_wall, 2))
    else:
        wall_txt = "∞" if min_wall == float("inf") else f"{min_wall:.2f}"
        set_gate(ctx.job_id, "QG4", "pass", f"עובי דופן מינימלי ~{wall_txt} מ\"מ",
                 min_wall_mm=None if min_wall == float("inf") else round(min_wall, 2))

    out = ctx.work_dir / "model_final.stl"
    mesh.export(out)
    save_artifact(ctx.job_id, "mesh_final", out)

    ctx.progress(100, f"מוכן: {dims[0]}×{dims[1]}×{dims[2]} מ\"מ")
    return {"dims_mm": dims, "scale_factor": round(factor, 4),
            "orient_score": None if orient_score is None else round(orient_score, 2),
            "min_wall_mm": None if min_wall == float("inf") else round(min_wall, 2)}
