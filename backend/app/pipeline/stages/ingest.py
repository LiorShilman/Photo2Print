"""שלב 1 — קליטה ואימות (F-1.1..F-1.6): magic bytes, גודל, רזולוציה."""
import filetype
from PIL import Image

from ...config import settings
from ...pipeline.context import GateFailure, StageContext
from ...storage import artifact_path, latest_artifact

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MESH_EXTS = {".stl", ".obj", ".3mf", ".ply", ".glb"}


def run(ctx: StageContext) -> dict:
    from ...db import db_session
    from ...models import Artifact, Job

    with db_session() as s:
        job = s.get(Job, ctx.job_id)
        input_type = job.input_type
        uploads = s.query(Artifact).filter_by(job_id=ctx.job_id, kind="upload").all()

    if not uploads:
        raise GateFailure("QG0", "לא נמצאו קבצים שהועלו")

    ctx.progress(20, "בודק פורמט וגודל קבצים…")
    validated = []
    for art in uploads:
        path = artifact_path(art)
        size_mb = path.stat().st_size / (1024 * 1024)
        ext = path.suffix.lower()

        if input_type in ("image", "multi_image"):
            if size_mb > settings.max_image_mb:
                raise GateFailure("QG0", f"התמונה {art.filename} גדולה מ-{settings.max_image_mb}MB")
            kind = filetype.guess(str(path))
            mime = kind.mime if kind else ""
            if mime not in IMAGE_MIMES:
                raise GateFailure(
                    "QG0",
                    f"הקובץ {art.filename} אינו תמונה נתמכת (זוהה: {mime or 'לא ידוע'})",
                    ["פורמטים נתמכים: JPG, PNG, WEBP, HEIC"],
                )
            with Image.open(path) as im:
                w, h = im.size
                if min(w, h) < 512:
                    raise GateFailure(
                        "QG0",
                        f"רזולוציה נמוכה מדי ({w}×{h}) — מינימום 512×512",
                        ["צלם מחדש ברזולוציה גבוהה יותר"],
                    )
                # תמונה ריקה/שחורה (F-1.5)
                gray = im.convert("L").resize((64, 64))
                px = list(gray.getdata())
                if max(px) - min(px) < 8:
                    raise GateFailure("QG0", "התמונה נראית ריקה או אחידה לחלוטין",
                                      ["ודא שהחפץ נראה בבירור בתמונה"])
            validated.append({"file": art.filename, "size_mb": round(size_mb, 2), "px": f"{w}x{h}"})
        else:  # mesh
            if size_mb > settings.max_upload_mb:
                raise GateFailure("QG0", f"הקובץ גדול מ-{settings.max_upload_mb}MB")
            if ext not in MESH_EXTS:
                raise GateFailure("QG0", f"פורמט תלת-ממד לא נתמך: {ext}",
                                  ["פורמטים נתמכים: STL, OBJ, 3MF, PLY, GLB"])
            # אימות טעינה בסיסי — magic bytes של קבצי mesh אינם אחידים,
            # לכן בודקים שהקובץ באמת נטען כרשת משולשים
            import trimesh
            try:
                m = trimesh.load(str(path), force="mesh")
                n_faces = len(m.faces)
            except Exception as e:
                raise GateFailure("QG0", f"הקובץ {art.filename} אינו קובץ תלת-ממד קריא: {e}")
            if n_faces == 0:
                raise GateFailure("QG0", "הקובץ לא מכיל גיאומטריה")
            validated.append({"file": art.filename, "size_mb": round(size_mb, 2), "faces": n_faces})

    ctx.progress(100, f"אומתו {len(validated)} קבצים")
    return {"validated": validated, "input_type": input_type}
