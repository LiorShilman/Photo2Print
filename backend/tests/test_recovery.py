"""בדיקות שחזור ג'ובים יתומים אחרי הפעלה מחדש של השרת."""
import os
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def isolated_db(monkeypatch):
    """DB זמני נפרד לכל בדיקה — לא נוגע בנתונים אמיתיים.

    settings הוא _SettingsProxy עם singleton ברמת המחלקה (לא המופע) —
    יש למקד את ה-monkeypatch שם כדי שהחלפת ה-DB אכן תתפוס.
    """
    from app import config, db

    tmp = Path(tempfile.mkdtemp())
    monkeypatch.setattr(config._SettingsProxy, "_instance", config.Settings(
        data_dir=tmp, db_url=f"sqlite:///{(tmp / 'test.db').as_posix()}",
    ))
    db._engine = None
    db._SessionLocal = None
    db.init_db()
    yield
    db._engine = None
    db._SessionLocal = None


def _make_job(status: str, stage_status: str | None = None):
    from app.db import db_session
    from app.models import Job, JobStage

    with db_session() as s:
        job = Job(input_type="mesh", status=status)
        s.add(job)
        s.flush()
        job_id = job.id
        if stage_status:
            s.add(JobStage(job_id=job_id, stage_name="slicing", stage_index=7,
                           status=stage_status))
    return job_id


def test_recovers_job_stuck_running(isolated_db):
    from app.db import db_session
    from app.models import Job
    from app.recovery import recover_orphaned_jobs

    job_id = _make_job("slicing", stage_status="running")
    count = recover_orphaned_jobs()
    assert count == 1
    with db_session() as s:
        job = s.get(Job, job_id)
        assert job.status == "failed"
        assert "מחדש" in job.error_he


def test_leaves_waiting_jobs_untouched(isolated_db):
    from app.db import db_session
    from app.models import Job
    from app.recovery import recover_orphaned_jobs

    job_id = _make_job("awaiting_scale")
    count = recover_orphaned_jobs()
    assert count == 0
    with db_session() as s:
        assert s.get(Job, job_id).status == "awaiting_scale"


def test_leaves_terminal_jobs_untouched(isolated_db):
    from app.db import db_session
    from app.models import Job
    from app.recovery import recover_orphaned_jobs

    done_id = _make_job("done")
    failed_id = _make_job("failed")
    count = recover_orphaned_jobs()
    assert count == 0
    with db_session() as s:
        assert s.get(Job, done_id).status == "done"
        assert s.get(Job, failed_id).status == "failed"
