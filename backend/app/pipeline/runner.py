"""ה-Runner — מריץ את שלבי הצנרת לפי סוג הקלט, אוכף Quality Gates.

הצנרת מפוצלת לשלושה מקטעים (כי סקייל ו-slicing דורשים קלט משתמש):
  A. generation:  ingest → preprocess → mesh_generation → mesh_repair   (אוטומטי)
  B. scale:       scale_orient + gates QG4/QG5                          (אחרי קלט מידה)
  C. slice:       slicing → package + gate QG6                          (אחרי בחירת פרופיל)
"""
import logging
import traceback

from ..jobqueue import progress_bus
from .context import GateFailure, StageContext, set_job
from .stages import ingest, mesh_generation, mesh_repair, package, preprocess, scale_orient, slicing

logger = logging.getLogger("p2p.runner")


def _fail_job(job_id: str, ctx: StageContext | None, exc: Exception):
    if isinstance(exc, GateFailure):
        error = {
            "gate": exc.gate,
            "message_he": exc.message_he,
            "suggestions_he": exc.suggestions_he,
        }
        message_he = f"נעצר בשער איכות {exc.gate}: {exc.message_he}"
    else:
        error = {"message_he": "שגיאה פנימית בעיבוד", "detail": str(exc)}
        message_he = f"שגיאה: {exc}"
        logger.error("Pipeline failed for %s:\n%s", job_id, traceback.format_exc())
    if ctx is not None:
        ctx.fail(error)
    set_job(job_id, status="failed", error_he=message_he)
    progress_bus.publish(job_id, {
        "job_id": job_id, "status": "failed", "stage": ctx.stage_name if ctx else "?",
        "stage_index": ctx.stage_index if ctx else 0, "total_stages": 8,
        "progress_pct": 100, "message_he": message_he, "error": error, "gates": {},
    })


def run_generation(job_id: str):
    """מקטע A — מהעלאה ועד mesh מתוקן. בסיום: awaiting_scale."""
    set_job(job_id, status="running", error_he=None)
    steps = [
        ("ingest", 1, ingest.run),
        ("preprocess", 2, preprocess.run),
        ("mesh_generation", 3, mesh_generation.run),
        ("mesh_repair", 4, mesh_repair.run),
    ]
    ctx = None
    try:
        for name, idx, fn in steps:
            ctx = StageContext(job_id, name, idx)
            ctx.start()
            metrics = fn(ctx) or {}
            if metrics.get("skipped"):
                ctx.finish(metrics)
                continue
            ctx.finish(metrics)
        set_job(job_id, status="awaiting_scale")
        progress_bus.publish(job_id, {
            "job_id": job_id, "status": "awaiting_scale", "stage": "mesh_repair",
            "stage_index": 4, "total_stages": 8, "progress_pct": 100,
            "message_he": "המודל מוכן! נא לקבוע מידות וכיוון הדפסה.", "gates": {},
        })
    except Exception as exc:
        _fail_job(job_id, ctx, exc)


def run_scale(job_id: str):
    """מקטע B — סקייל, אוריינטציה ושערי QG4/QG5. בסיום: awaiting_slice."""
    set_job(job_id, status="orienting", error_he=None)
    ctx = StageContext(job_id, "scale_orient", 5)
    try:
        ctx.start()
        metrics = scale_orient.run(ctx) or {}
        ctx.finish(metrics)
        set_job(job_id, status="awaiting_slice")
        progress_bus.publish(job_id, {
            "job_id": job_id, "status": "awaiting_slice", "stage": "scale_orient",
            "stage_index": 5, "total_stages": 8, "progress_pct": 100,
            "message_he": "מוכן ל-Slicing — בחר מדפסת ופריסט.", "gates": {},
        })
    except Exception as exc:
        _fail_job(job_id, ctx, exc)


def run_slice(job_id: str):
    """מקטע C — slicing, QG6 ואריזה. בסיום: done."""
    set_job(job_id, status="slicing", error_he=None)
    ctx = None
    try:
        ctx = StageContext(job_id, "slicing", 7)
        ctx.start()
        metrics = slicing.run(ctx) or {}
        ctx.finish(metrics)

        ctx = StageContext(job_id, "package", 8)
        ctx.start()
        metrics = package.run(ctx) or {}
        ctx.finish(metrics)

        set_job(job_id, status="done")
        progress_bus.publish(job_id, {
            "job_id": job_id, "status": "done", "stage": "package",
            "stage_index": 8, "total_stages": 8, "progress_pct": 100,
            "message_he": "הסתיים! חבילת ההדפסה מוכנה להורדה.", "gates": {},
        })
    except Exception as exc:
        _fail_job(job_id, ctx, exc)
