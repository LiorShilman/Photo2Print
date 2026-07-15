"""Artifacts API — הגשת קבצים (מודלים, previews, דוחות) ל-frontend."""
import mimetypes

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Artifact
from ..storage import artifact_path

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("/{artifact_id}")
def get_artifact(artifact_id: str, db: Session = Depends(get_db)):
    art = db.get(Artifact, artifact_id)
    if art is None:
        raise HTTPException(404, "ארטיפקט לא נמצא")
    path = artifact_path(art)
    if not path.is_file():
        raise HTTPException(410, "הקובץ נמחק מהאחסון")
    media = mimetypes.guess_type(art.filename)[0] or "application/octet-stream"
    return FileResponse(path, filename=art.filename, media_type=media)
