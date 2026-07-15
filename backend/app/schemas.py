"""סכמות API — Pydantic v2."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class GenOptions(BaseModel):
    quality: Literal["draft", "standard", "high"] = "standard"
    target_polycount: int = 100_000
    texture: bool = False
    symmetry_hint: bool | None = None


class ScaleRequest(BaseModel):
    axis: Literal["x", "y", "z"] = "z"
    size_mm: float = Field(gt=0.1, le=2000)
    rotation_deg: tuple[float, float, float] = (0, 0, 0)  # סיבוב ידני מה-gizmo
    auto_orient: bool = True
    flatten_base: bool = False


class AdvancedSliceOptions(BaseModel):
    layer_height: float | None = Field(default=None, gt=0.04, le=0.6)
    infill_pct: int | None = Field(default=None, ge=0, le=100)
    infill_pattern: str | None = None       # grid/gyroid/honeycomb...
    supports: Literal["auto", "tree", "off"] | None = None
    brim: bool | None = None
    raft: bool | None = None
    perimeters: int | None = Field(default=None, ge=1, le=10)
    nozzle_temp: int | None = Field(default=None, ge=150, le=320)
    bed_temp: int | None = Field(default=None, ge=0, le=130)


class SliceRequest(BaseModel):
    profile_id: str
    preset: Literal["draft", "standard", "quality"] = "standard"
    material: Literal["PLA", "PETG", "TPU"] = "PLA"
    advanced: AdvancedSliceOptions | None = None


class ArtifactOut(BaseModel):
    id: str
    kind: str
    filename: str
    size_bytes: int
    sha256: str

    model_config = {"from_attributes": True}


class StageOut(BaseModel):
    stage_name: str
    stage_index: int
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    metrics_json: dict
    error_json: dict | None

    model_config = {"from_attributes": True}


class JobOut(BaseModel):
    id: str
    status: str
    input_type: str
    source_provider: str | None
    image_score: float | None
    ai_confidence: float | None
    error_he: str | None
    gates_json: dict
    scale_json: dict | None
    slice_json: dict | None
    print_stats_json: dict | None
    profile_id: str | None
    created_at: datetime
    stages: list[StageOut] = []
    artifacts: list[ArtifactOut] = []

    model_config = {"from_attributes": True}


class ProfileOut(BaseModel):
    id: str
    name: str
    vendor: str
    bed_x: float
    bed_y: float
    bed_z: float
    nozzle_mm: float
    is_builtin: bool

    model_config = {"from_attributes": True}


class ProfileIn(BaseModel):
    name: str
    vendor: str = ""
    bed_x: float = Field(gt=50, le=1000)
    bed_y: float = Field(gt=50, le=1000)
    bed_z: float = Field(gt=50, le=1000)
    nozzle_mm: float = Field(default=0.4, gt=0.1, le=1.2)
    slicer_ini_base: str = "generic_fdm.ini"
