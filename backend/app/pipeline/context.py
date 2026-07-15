"""הקשר ריצה של שלב pipeline — עדכון DB + פרסום progress במקום אחד."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import settings
from ..db import db_session
from ..jobqueue import progress_bus
from ..models import Job, JobStage


class GateFailure(Exception):
    """כשל שער איכות — עוצר את הצנרת עם הסבר בעברית (Zero-Guess Policy)."""

    def __init__(self, gate: str, message_he: str, suggestions_he: list[str] | None = None):
        super().__init__(f"{gate}: {message_he}")
        self.gate = gate
        self.message_he = message_he
        self.suggestions_he = suggestions_he or []


STAGE_NAMES_HE = {
    "ingest": "קליטת קבצים ואימות",
    "preprocess": "עיבוד תמונה מקדים",
    "mesh_generation": "יצירת גיאומטריה תלת-ממדית",
    "mesh_repair": "תיקון רשת המשולשים",
    "scale_orient": "סקייל ואוריינטציה",
    "quality_gates": "בדיקת שערי איכות",
    "slicing": "פריסה לשכבות (Slicing)",
    "package": "אריזת התוצרים והדוח",
}

TOTAL_STAGES = 8


@dataclass
class StageContext:
    job_id: str
    stage_name: str
    stage_index: int
    work_dir: Path = field(init=False)

    def __post_init__(self):
        self.work_dir = Path(settings.data_dir) / "work" / self.job_id
        self.work_dir.mkdir(parents=True, exist_ok=True)

    # --- עדכוני DB ---

    def _get_or_create_stage(self, s) -> JobStage:
        st = (
            s.query(JobStage)
            .filter_by(job_id=self.job_id, stage_name=self.stage_name)
            .first()
        )
        if st is None:
            st = JobStage(
                job_id=self.job_id,
                stage_name=self.stage_name,
                stage_index=self.stage_index,
            )
            s.add(st)
        return st

    def start(self):
        with db_session() as s:
            st = self._get_or_create_stage(s)
            st.status = "running"
            st.started_at = datetime.now(timezone.utc)
            st.error_json = None
        self.progress(0, STAGE_NAMES_HE.get(self.stage_name, self.stage_name) + "…")

    def finish(self, metrics: dict[str, Any] | None = None):
        with db_session() as s:
            st = self._get_or_create_stage(s)
            st.status = "done"
            st.finished_at = datetime.now(timezone.utc)
            if metrics:
                st.metrics_json = {**(st.metrics_json or {}), **metrics}

    def fail(self, error: dict[str, Any]):
        with db_session() as s:
            st = self._get_or_create_stage(s)
            st.status = "failed"
            st.finished_at = datetime.now(timezone.utc)
            st.error_json = error

    # --- progress ל-WS (חוזה לפי PRD §6.3) ---

    def progress(self, pct: int, message_he: str):
        with db_session() as s:
            job = s.get(Job, self.job_id)
            gates = dict(job.gates_json or {}) if job else {}
            status = job.status if job else "unknown"
        progress_bus.publish(self.job_id, {
            "job_id": self.job_id,
            "status": status,
            "stage": self.stage_name,
            "stage_index": self.stage_index,
            "total_stages": TOTAL_STAGES,
            "progress_pct": pct,
            "message_he": message_he,
            "gates": {k: v.get("status") for k, v in gates.items()},
        })


def set_job(job_id: str, **fields):
    with db_session() as s:
        job = s.get(Job, job_id)
        for k, v in fields.items():
            setattr(job, k, v)


def get_job_field(job_id: str, field_name: str):
    with db_session() as s:
        job = s.get(Job, job_id)
        return getattr(job, field_name) if job else None


def set_gate(job_id: str, gate: str, status: str, message_he: str = "", **extra):
    """עדכון תוצאת שער איכות על הג'וב + פרסום מיידי."""
    with db_session() as s:
        job = s.get(Job, job_id)
        gates = dict(job.gates_json or {})
        gates[gate] = {"status": status, "message_he": message_he, **extra}
        job.gates_json = gates
