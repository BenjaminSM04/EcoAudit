"""Modelo de datos.

Regla de privacidad: no se guarda ningún dato identificable del paciente. ``Case.patient_ref``
es un seudónimo que asigna el usuario; las imágenes se almacenan re-codificadas, sin metadatos.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator):
    """Fecha y hora siempre en UTC y con zona. SQLite descarta la zona al guardar; aquí se repone
    al leer, para que la API nunca entregue una hora ambigua."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Se requiere una fecha con zona horaria.")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class Role(enum.StrEnum):
    medico = "medico"
    investigador = "investigador"
    admin = "admin"


class AnalysisStatus(enum.StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class CohortStatus(enum.StrEnum):
    processing = "processing"
    done = "done"
    failed = "failed"


class CohortSource(enum.StrEnum):
    analyses = "analyses"  # desde análisis existentes (CSV)
    batch = "batch"  # lote nuevo de imágenes


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    # Los tokens emitidos antes de este instante dejan de valer (ver ``deps.get_current_user``).
    password_changed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_ref: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    created_by: Mapped[User] = relationship()
    images: Mapped[list[Image]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="Image.id"
    )


class Image(Base):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    pixel_sha256: Mapped[str] = mapped_column(String(64), index=True)
    dhash: Mapped[str] = mapped_column(String(16))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    source_format: Mapped[str] = mapped_column(String(16))
    qc_flags: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="images")
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="image", cascade="all, delete-orphan", order_by="Analysis.id"
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(40))
    bundle_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    card: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    status: Mapped[AnalysisStatus] = mapped_column(
        Enum(AnalysisStatus, native_enum=False, length=20),
        default=AnalysisStatus.pending,
        index=True,
    )
    roi: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x, y, w, h} en píxeles
    # Veces que un worker lo reclamó; si el worker muere se reencola hasta agotar los intentos.
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    probability_raw: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)  # calibrada
    member_spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shift_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    cam_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    image: Mapped[Image] = relationship(back_populates="analyses")
    model_version: Mapped[ModelVersion] = relationship()


class ClinicalReading(Base):
    """Lectura independiente de un análisis, una por lector."""

    __tablename__ = "clinical_readings"
    __table_args__ = (
        UniqueConstraint("analysis_id", "reader_id", name="uq_reading_analysis_reader"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"))
    reader_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    birads: Mapped[str] = mapped_column(String(2))
    blinded: Mapped[bool] = mapped_column(Boolean)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)


class Cohort(Base):
    """Cohorte de auditoría: un conjunto de análisis con etiqueta y las métricas que resultan.

    Con ``source = batch`` nace en ``processing`` y se cierra cuando termina el último análisis
    (``cohorts.refresh_cohort``). Con ``source = analyses`` nace ya terminada.
    """

    __tablename__ = "cohorts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    source: Mapped[CohortSource] = mapped_column(Enum(CohortSource, native_enum=False, length=16))
    status: Mapped[CohortStatus] = mapped_column(
        Enum(CohortStatus, native_enum=False, length=16),
        default=CohortStatus.processing,
        index=True,
    )
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"))
    csv_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 del CSV (o del manifiesto)
    results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    owner: Mapped[User] = relationship()
    model_version: Mapped[ModelVersion] = relationship()
    items: Mapped[list[CohortItem]] = relationship(
        back_populates="cohort", cascade="all, delete-orphan", order_by="CohortItem.id"
    )


class CohortItem(Base):
    """Un análisis de la cohorte con su etiqueta y el seudónimo del paciente."""

    __tablename__ = "cohort_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    cohort_id: Mapped[int] = mapped_column(ForeignKey("cohorts.id"), index=True)
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"), index=True)
    patient_ref: Mapped[str] = mapped_column(String(64))
    label: Mapped[int] = mapped_column(Integer)  # 0 benigno, 1 maligno

    cohort: Mapped[Cohort] = relationship(back_populates="items")
    analysis: Mapped[Analysis] = relationship()


class AuditLog(Base):
    """Bitácora de acciones: quién hizo qué y cuándo. Solo se agrega, nunca se edita."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
