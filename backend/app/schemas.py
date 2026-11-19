"""Esquemas de entrada y salida de la API."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import AnalysisStatus, CohortSource, CohortStatus, Role


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(_Out):
    id: int
    email: str
    full_name: str
    role: Role
    is_active: bool


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10, max_length=128)
    role: Role


class UserUpdate(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=10, max_length=128)


class PasswordReset(BaseModel):
    new_password: str = Field(min_length=10, max_length=128)


class Roi(BaseModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    w: float = Field(gt=0)
    h: float = Field(gt=0)


class AnalysisCreate(BaseModel):
    roi: Roi | None = None


class AnalysisOut(_Out):
    id: int
    image_id: int
    status: AnalysisStatus
    attempts: int
    roi: Roi | None
    model_version_id: int
    probability_raw: float | None
    probability: float | None
    member_spread: float | None
    decision: str | None
    shift_score: float | None
    shift_flag: bool | None
    warnings: list[str]
    has_cam: bool
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class ImageOut(_Out):
    id: int
    case_id: int
    width: int
    height: int
    source_format: str
    qc_flags: list[str]
    duplicate_of_id: int | None
    created_at: datetime
    analyses: list[AnalysisOut] = []


class CaseCreate(BaseModel):
    patient_ref: str = Field(
        min_length=1,
        max_length=64,
        description="Seudónimo del paciente. No ingrese nombre, CI ni otros datos personales.",
    )
    notes: str = Field(default="", max_length=4000)


class CaseSummary(_Out):
    id: int
    patient_ref: str
    notes: str
    created_at: datetime
    image_count: int


class CaseOut(_Out):
    id: int
    patient_ref: str
    notes: str
    created_at: datetime
    images: list[ImageOut]


class ModelVersionOut(_Out):
    id: int
    name: str
    version: str
    bundle_sha256: str
    is_active: bool
    card: dict
    created_at: datetime


class CohortProgress(BaseModel):
    total: int
    done: int
    failed: int


class CohortSummary(_Out):
    id: int
    name: str
    source: CohortSource
    status: CohortStatus
    model: str  # "nombre versión"
    created_at: datetime
    progress: CohortProgress


class CohortBin(BaseModel):
    bin: int
    n: int
    predicted: float
    observed: float


class CohortMetrics(BaseModel):
    patients: int
    positive: int
    images: int
    auc: float
    ci: tuple[float, float] | None
    brier: float
    ece: float
    bins: list[CohortBin]
    abstentions: int
    decisions: dict[str, int]  # conteo por decisión
    demo: bool
    model_hash: str
    csv_hash: str


class CohortDetail(CohortSummary):
    results: CohortMetrics | None
    error: str | None
