"""שלב 3 — יצירת Mesh דרך אבסטרקציית ספקים, כולל retry ו-fallback (F-3.1..F-3.6)."""
import time

from ...config import settings
from ...schemas import GenOptions
from ...storage import artifact_path, latest_artifact, save_artifact
from ..context import GateFailure, StageContext, set_gate, set_job
from ..providers import ProviderError, get_provider

MAX_RETRIES = 2


def _try_provider(name: str, ctx: StageContext, image_path, opts) -> "RawMeshResult | None":
    """הרצת ספק עם עד 2 נסיונות חוזרים ו-backoff."""
    for attempt in range(1 + MAX_RETRIES):
        try:
            provider = get_provider(name)
            return provider.generate(image_path, ctx.work_dir, opts, ctx.progress)
        except ProviderError as e:
            if not e.retryable or attempt == MAX_RETRIES:
                ctx.progress(5, f"ספק {name} נכשל: {e.message_he}")
                return None
            wait = 2 ** (attempt + 1)
            ctx.progress(5, f"ספק {name} נכשל, מנסה שוב בעוד {wait} שניות…")
            time.sleep(wait)
    return None


def run(ctx: StageContext) -> dict:
    from ...db import db_session
    from ...models import Job

    with db_session() as s:
        job = s.get(Job, ctx.job_id)
        input_type = job.input_type

    if input_type == "mesh":
        # UC-3: קובץ קיים — הוא ה-mesh הגולמי
        upload = latest_artifact(ctx.job_id, "upload")
        save_artifact(ctx.job_id, "mesh_raw", artifact_path(upload))
        set_job(ctx.job_id, source_provider="user_upload", ai_confidence=1.0)
        set_gate(ctx.job_id, "QG2", "pass", "קובץ שהועלה ישירות — ללא AI")
        ctx.progress(100, "משתמש בקובץ התלת-ממד שהועלה")
        return {"skipped_ai": True}

    image = latest_artifact(ctx.job_id, "image_processed")
    image_path = artifact_path(image)
    opts = GenOptions()

    primary = settings.mesh_provider
    fallback = settings.mesh_fallback_provider

    result = _try_provider(primary, ctx, image_path, opts)
    if result is None and fallback and fallback != primary:
        ctx.progress(8, f"עובר לספק גיבוי: {fallback}")
        result = _try_provider(fallback, ctx, image_path, opts)

    if result is None:
        raise GateFailure(
            "QG2", "כל ספקי יצירת המודל נכשלו",
            ["בדוק מפתחות API ב-.env", "נסה שוב מאוחר יותר",
             "או עבור לספק local_extrude (ללא מפתח)"],
        )

    save_artifact(ctx.job_id, "mesh_raw", result.mesh_path)
    set_job(ctx.job_id, source_provider=result.provider, ai_confidence=result.confidence)

    # QG-2: confidence < 0.35 → אזהרה בולטת
    if result.confidence < 0.35:
        set_gate(ctx.job_id, "QG2", "warn",
                 f"ביטחון הספק נמוך ({result.confidence:.2f}) — מומלץ תמונות נוספות/טובות יותר",
                 confidence=result.confidence)
    else:
        note = result.metadata.get("note_he", "")
        status = "warn" if result.provider == "local_extrude" else "pass"
        set_gate(ctx.job_id, "QG2", status,
                 note or f"ביטחון הספק: {result.confidence:.2f}", confidence=result.confidence)

    ctx.progress(100, f"המודל נוצר על ידי {result.provider}")
    return {"provider": result.provider, "confidence": result.confidence, **result.metadata}
