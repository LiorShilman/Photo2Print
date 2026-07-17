"""מודל הנתונים — jobs, job_stages, artifacts, printer_profiles (לפי PRD §7)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: _uid("j"))
    # pending → running → awaiting_scale → orienting → awaiting_slice → slicing → done | failed
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    input_type: Mapped[str] = mapped_column(String(16))  # image | multi_image | mesh | lithophane | text
    text_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)  # אם input_type="text"
    source_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_he: Mapped[str | None] = mapped_column(Text, nullable=True)
    gates_json: Mapped[dict] = mapped_column(JSON, default=dict)          # {"QG1": {"status": "pass", ...}}
    lithophane_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # אפשרויות ליתופן (אם input_type="lithophane")
    scale_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # קלט המשתמש האחרון
    slice_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # פרמטרי slicing אחרונים
    print_stats_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    stages: Mapped[list["JobStage"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobStage(Base):
    __tablename__ = "job_stages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    stage_name: Mapped[str] = mapped_column(String(32))
    stage_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed|skipped
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    job: Mapped[Job] = relationship(back_populates="stages")


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: _uid("a"))
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # upload|image_processed|mesh_raw|mesh_repaired|mesh_final|gcode|preview|report|zip|slicer_ini
    filename: Mapped[str] = mapped_column(String(255))
    rel_path: Mapped[str] = mapped_column(String(500))  # יחסי ל-storage_dir
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job: Mapped[Job] = relationship(back_populates="artifacts")


class PrinterProfile(Base):
    __tablename__ = "printer_profiles"

    id: Mapped[str] = mapped_column(String(20), primary_key=True, default=lambda: _uid("p"))
    name: Mapped[str] = mapped_column(String(64), unique=True)
    vendor: Mapped[str] = mapped_column(String(32), default="")
    bed_x: Mapped[float] = mapped_column(Float)
    bed_y: Mapped[float] = mapped_column(Float)
    bed_z: Mapped[float] = mapped_column(Float)
    nozzle_mm: Mapped[float] = mapped_column(Float, default=0.4)
    slicer_ini_base: Mapped[str] = mapped_column(String(64))  # שם קובץ ב-backend/profiles
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
