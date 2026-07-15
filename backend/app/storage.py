"""אחסון ארטיפקטים בדיסק מקומי — כל קובץ נשמר עם hash לפי ADR-5."""
import hashlib
import shutil
from pathlib import Path

from .config import settings
from .db import db_session
from .models import Artifact


def _job_dir(job_id: str) -> Path:
    d = Path(settings.storage_dir) / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_artifact(job_id: str, kind: str, src: Path, filename: str | None = None) -> Artifact:
    """מעתיק קובץ לאחסון הג'וב ורושם artifact ב-DB. מחזיר את הרשומה."""
    filename = filename or src.name
    dest = _job_dir(job_id) / filename
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    art = Artifact(
        job_id=job_id,
        kind=kind,
        filename=filename,
        rel_path=f"{job_id}/{filename}",
        sha256=sha256_of(dest),
        size_bytes=dest.stat().st_size,
    )
    with db_session() as s:
        s.add(art)
    return art


def save_artifact_bytes(job_id: str, kind: str, filename: str, data: bytes) -> Artifact:
    dest = _job_dir(job_id) / filename
    dest.write_bytes(data)
    return save_artifact(job_id, kind, dest, filename)


def artifact_path(art: Artifact) -> Path:
    return Path(settings.storage_dir) / art.rel_path


def latest_artifact(job_id: str, kind: str) -> Artifact | None:
    with db_session() as s:
        return (
            s.query(Artifact)
            .filter_by(job_id=job_id, kind=kind)
            .order_by(Artifact.created_at.desc(), Artifact.id.desc())
            .first()
        )


def delete_job_files(job_id: str):
    d = Path(settings.storage_dir) / job_id
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
