"""שחזור ג'ובים יתומים בעליית שרת.

תור העבודות הוא in-process (ThreadPoolExecutor) ולא persistent — אם
התהליך מת/מופעל מחדש באמצע עיבוד, ה-thread נעלם בלי שהג'וב יתעדכן.
בלי הטיפול הזה, ג'וב כזה נשאר תקוע על progress bar אינסופי ב-UI.

סטטוסים "בעיבוד פעיל" (worker thread אמור לרוץ): pending, running,
orienting, slicing. awaiting_scale / awaiting_slice הם מצבי המתנה
לגיטימיים לקלט משתמש — לא נוגעים בהם.
"""
import logging

from .db import db_session
from .models import Job, JobStage

logger = logging.getLogger("p2p.recovery")

_IN_PROGRESS_STATUSES = ("pending", "running", "orienting", "slicing")
_RECOVERY_MESSAGE_HE = "השרת הופעל מחדש באמצע העיבוד. נסה שוב."


def recover_orphaned_jobs() -> int:
    """מסמן ככשל כל ג'וב שנשאר 'תקוע' מהרצה קודמת. מחזיר כמות שטופלה."""
    with db_session() as s:
        orphans = s.query(Job).filter(Job.status.in_(_IN_PROGRESS_STATUSES)).all()
        for job in orphans:
            running_stage = (
                s.query(JobStage)
                .filter_by(job_id=job.id, status="running")
                .first()
            )
            if running_stage:
                running_stage.status = "failed"
                running_stage.error_json = {"message_he": _RECOVERY_MESSAGE_HE}
            job.status = "failed"
            job.error_he = _RECOVERY_MESSAGE_HE
        if orphans:
            logger.warning("Recovered %d orphaned job(s) after restart: %s",
                           len(orphans), [j.id for j in orphans])
        return len(orphans)
