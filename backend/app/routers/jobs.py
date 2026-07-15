"""Jobs API — יצירה, סטטוס, סקייל, slicing, הורדות (PRD §7)."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..jobqueue import enqueue
from ..models import Artifact, Job
from ..pipeline import runner
from ..schemas import JobOut, ScaleRequest, SliceRequest
from ..storage import artifact_path, delete_job_files, save_artifact_bytes

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
MESH_EXTS = {".stl", ".obj", ".3mf", ".ply", ".glb"}


def _detect_input_type(files: list[UploadFile]) -> str:
    """F-1.6 — זיהוי מסלול אוטומטי."""
    exts = {Path(f.filename or "").suffix.lower() for f in files}
    if exts & MESH_EXTS:
        if len(files) > 1:
            raise HTTPException(400, "ניתן להעלות קובץ תלת-ממד אחד בלבד")
        return "mesh"
    if not exts <= IMAGE_EXTS:
        raise HTTPException(400, f"פורמט לא נתמך: {', '.join(exts - IMAGE_EXTS)}")
    return "image" if len(files) == 1 else "multi_image"


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    files: list[UploadFile],
    profile_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(400, "לא הועלו קבצים")
    input_type = _detect_input_type(files)
    if input_type == "multi_image":
        raise HTTPException(400, "מסלול ריבוי תמונות (פוטוגרמטריה) יגיע בגרסה 1.5")

    # קריאת הקבצים לפני יצירת הרשומה — ולידציית גודל מוקדמת
    max_bytes = settings.max_upload_mb * 1024 * 1024
    payloads: list[tuple[str, bytes]] = []
    for i, f in enumerate(files):
        data = await f.read()
        if len(data) > max_bytes:
            raise HTTPException(413, f"הקובץ {f.filename} גדול מ-{settings.max_upload_mb}MB")
        payloads.append((f"upload_{i}{Path(f.filename or 'file').suffix.lower()}", data))

    job = Job(input_type=input_type, profile_id=profile_id, status="pending")
    db.add(job)
    db.commit()  # הארטיפקטים נשמרים בסשן נפרד — הג'וב חייב להיות persist קודם (FK)

    for safe, data in payloads:
        save_artifact_bytes(job.id, "upload", safe, data)
    enqueue(runner.run_generation, job.id)
    return _job_out(db, job.id)


def _job_out(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "ג'וב לא נמצא")
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), limit: int = 50):
    return (db.query(Job).order_by(Job.created_at.desc()).limit(min(limit, 200)).all())


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    return _job_out(db, job_id)


@router.post("/{job_id}/scale", response_model=JobOut)
def set_scale(job_id: str, req: ScaleRequest, db: Session = Depends(get_db)):
    job = _job_out(db, job_id)
    if job.status not in ("awaiting_scale", "awaiting_slice", "done", "failed"):
        raise HTTPException(409, f"הג'וב בסטטוס {job.status} — יש להמתין לסיום העיבוד")
    job.scale_json = req.model_dump()
    job.status = "orienting"
    db.commit()
    enqueue(runner.run_scale, job_id)
    return job


@router.post("/{job_id}/slice", response_model=JobOut)
def run_slice(job_id: str, req: SliceRequest, db: Session = Depends(get_db)):
    job = _job_out(db, job_id)
    if job.status not in ("awaiting_slice", "done", "failed"):
        raise HTTPException(409, f"הג'וב בסטטוס {job.status} — קבע קודם מידות (scale)")
    job.slice_json = req.model_dump()
    job.profile_id = req.profile_id
    job.status = "slicing"
    db.commit()
    enqueue(runner.run_slice, job_id)
    return job


@router.post("/{job_id}/duplicate", response_model=JobOut, status_code=201)
def duplicate_job(job_id: str, db: Session = Depends(get_db)):
    """UC-4 — שכפול ג'וב (מעתיק קלט ומריץ מחדש)."""
    src = _job_out(db, job_id)
    new = Job(input_type=src.input_type, profile_id=src.profile_id,
              scale_json=src.scale_json, status="pending")
    db.add(new)
    db.commit()  # persist לפני שמירת ארטיפקטים בסשן נפרד (FK)
    uploads = db.query(Artifact).filter_by(job_id=job_id, kind="upload").all()
    for art in uploads:
        save_artifact_bytes(new.id, "upload", art.filename, artifact_path(art).read_bytes())
    enqueue(runner.run_generation, new.id)
    return new


@router.get("/{job_id}/gcode_layers")
def gcode_layers(job_id: str, db: Session = Depends(get_db)):
    """שכבות ה-G-code ל-preview אינטראקטיבי (F-7.7)."""
    from ..pipeline.gcode_preview import parse_layers

    art = (db.query(Artifact).filter_by(job_id=job_id, kind="gcode")
           .order_by(Artifact.created_at.desc()).first())
    if art is None:
        raise HTTPException(404, "אין עדיין G-code לג'וב זה")
    layers = parse_layers(artifact_path(art))
    return {"layers": layers, "count": len(layers)}


@router.get("/{job_id}/download")
def download_zip(job_id: str, db: Session = Depends(get_db)):
    art = (db.query(Artifact).filter_by(job_id=job_id, kind="zip")
           .order_by(Artifact.created_at.desc()).first())
    if art is None:
        raise HTTPException(404, "ה-ZIP עדיין לא נוצר")
    return FileResponse(artifact_path(art), filename=art.filename,
                        media_type="application/zip")


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_out(db, job_id)
    db.delete(job)
    db.commit()
    delete_job_files(job_id)
