"""Datos sintéticos reproducibles para recorrer los flujos de EcoAudit."""

import hashlib
import io
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image as PilImage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .cohorts import Entry, build_results
from .db import new_session
from .deps import record
from .devtools import make_demo_bundle
from .models import (
    Analysis,
    AnalysisStatus,
    Case,
    CaseReader,
    ClinicalReading,
    Cohort,
    CohortItem,
    CohortSource,
    CohortStatus,
    Image,
    ModelVersion,
    Role,
    User,
    utcnow,
)
from .pipeline.bundle import ModelBundle
from .pipeline.runner import analyze
from .registry import get_active, register_bundle
from .security import hash_password
from .services import DuplicateFinder, prepare_image, store_image
from .storage import get_storage

_ACCOUNTS = (
    ("admin", "Administración de demostración", Role.admin),
    ("medico1", "Ana Rojas", Role.medico),
    ("medico2", "Luis Flores", Role.medico),
    ("investigador", "Investigación de demostración", Role.investigador),
)
_NOTES = "Ecografías sintéticas de demostración."
_COHORT = "Auditoría de demostración (imágenes sintéticas)"


def _users(db: Session, password: str) -> list[User]:
    users = []
    for alias, name, role in _ACCOUNTS:
        email = f"{alias}@ecoaudit.test"
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email, full_name=name, role=role, password_hash=hash_password(password)
            )
            db.add(user)
            db.flush()
            record(db, None, "user_created", "user", user.id, role=role, via="seed-demo")
        if user.role != role:
            raise ValueError(f"La cuenta {email} tiene un rol diferente al esperado.")
        users.append(user)
    return users


def _ultrasound(seed: int, irregular: bool) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[:320, :416]
    dx = (x - rng.uniform(155, 260)) / rng.uniform(45, 68)
    dy = (y - rng.uniform(105, 195)) / rng.uniform(24, 39)
    angle = np.arctan2(dy, dx)
    edge = 1 + (0.16 * np.sin(5 * angle) + 0.11 * np.cos(3 * angle) if irregular else 0)
    lesion = np.hypot(dx, dy) < edge
    layers = 10 * np.sin(y / 12 + 0.7 * np.cos(x / 61)) + 6 * np.cos(y / 4 + x / 70)
    tissue = rng.uniform(70, 142) - 0.15 * y + layers
    tissue += 45 * np.exp(-(((y - 22 - 5 * np.cos(x / 55)) / 4) ** 2))
    tissue = np.where(lesion, tissue * 0.31, tissue)
    if irregular:
        tissue = np.where((dy > 0.8) & (np.abs(dx) < 0.78), tissue * 0.75, tissue)
    speckle = rng.rayleigh(0.77, size=tissue.shape)
    return np.clip(tissue * speckle + rng.normal(3, 3, size=tissue.shape), 0, 255).astype(np.uint8)


def _demo_analysis(
    image: Image,
    model: ModelVersion,
    bundle: ModelBundle,
    pixels: np.ndarray,
    requested: datetime,
    processing_ms: int,
) -> tuple[Analysis, bytes]:
    result = analyze(np.repeat(pixels[:, :, None], 3, axis=2), None, bundle)
    analysis = Analysis(
        image=image,
        requested_by_id=image.case.created_by_id,
        model_version_id=model.id,
        status=AnalysisStatus.done,
        attempts=1,
        created_at=requested,
        started_at=requested + timedelta(milliseconds=150),
        finished_at=requested + timedelta(milliseconds=150 + processing_ms),
        probability_raw=result.probability_raw,
        probability=result.probability,
        member_spread=result.member_spread,
        decision=result.decision,
        shift_flag=result.shift_flag,
        shift_score=result.shift_score,
        warnings=[*result.warnings, *image.qc_flags],
    )
    return analysis, result.cam_overlay_png


def _demo_readings(analysis: Analysis, readers: tuple[User, User], index: int, label: int):
    categories = ("2", "3") if label == 0 else ("4A", "4B")
    for position, reader in enumerate(readers):
        category = categories[(index + position * (index % 3 == 0)) % 2]
        if position == 1 and index % 7 == 0:
            category = "4A" if label == 0 else "3"
        yield ClinicalReading(
            analysis_id=analysis.id,
            reader_id=reader.id,
            birads=category,
            blinded=(index + position) % 3 != 0,
            created_at=analysis.created_at + timedelta(minutes=2),
        )


def seed_demo(password: str) -> int:
    storage = get_storage()
    written = []
    with new_session() as db:
        # Dos invocaciones simultáneas deben observar el mismo conjunto de demostración.
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        elif db.get_bind().dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(4543242)"))
        admin, first, second, researcher = _users(db, password)
        active = get_active(db)
        model = active if active is not None and active.card.get("demo") else None
        if model is None:
            with TemporaryDirectory(prefix="ecoaudit-demo-") as directory:
                model = register_bundle(
                    db, make_demo_bundle(Path(directory)), activate=active is None
                )
        now = utcnow()
        bundle = None
        created = 0
        cohort_rows = []
        finders = {owner.id: DuplicateFinder(db, owner.id) for owner in (first, second, researcher)}
        try:
            for index in range(20):
                owner = researcher if index >= 12 else (first, second)[index % 2]
                reference = f"PAC-{9100 + index:04}"
                label = (index // 2) % 2
                case = db.scalar(
                    select(Case).where(
                        Case.created_by_id == owner.id,
                        Case.patient_ref == reference,
                        Case.notes == _NOTES,
                    )
                )
                if case is None:
                    created += 1
                    if bundle is None:
                        bundle = ModelBundle(storage.path(model.storage_key))
                    when = now - timedelta(days=index * 29 / 19, minutes=10)
                    case = Case(
                        patient_ref=reference, notes=_NOTES, created_by_id=owner.id, created_at=when
                    )
                    db.add(case)
                    db.flush()
                    for reader in (first, second):
                        if reader.id != owner.id and index % 5 != 4:
                            db.add(
                                CaseReader(
                                    case_id=case.id,
                                    reader_id=reader.id,
                                    assigned_by=admin.id,
                                    created_at=when,
                                )
                            )
                    for frame in range(1 + index % 3):
                        pixels = _ultrasound(index * 3 + frame, bool(label))
                        buffer = io.BytesIO()
                        PilImage.fromarray(pixels).save(buffer, format="PNG")
                        image = store_image(
                            db, case, prepare_image(buffer.getvalue(), "eco.png"), finders[owner.id]
                        )
                        written.append(image.storage_key)
                        image.created_at = when
                        requested = when + timedelta(seconds=frame)
                        analysis, cam = _demo_analysis(
                            image, model, bundle, pixels, requested, 400 + 70 * index
                        )
                        db.add(analysis)
                        db.flush()
                        analysis.cam_key = f"cams/{analysis.id}.png"
                        written.append(analysis.cam_key)
                        storage.put_bytes(analysis.cam_key, cam)
                        if frame == 0 and index % 5 != 4:
                            db.add_all(_demo_readings(analysis, (first, second), index, label))
                if owner == researcher:
                    cohort_rows.extend(
                        (reference, label, analysis)
                        for image in case.images
                        for analysis in image.analyses
                        if analysis.model_version_id == model.id
                        and analysis.probability is not None
                    )
            _seed_cohort(db, researcher, model, cohort_rows, now)
            if created:
                record(db, admin, "demo_seeded", "case", count=created)
            db.commit()
        except Exception:
            for key in written:
                storage.delete(key)
            raise
    return created


def _seed_cohort(
    db: Session,
    researcher: User,
    model: ModelVersion,
    rows: list[tuple[str, int, Analysis]],
    now: datetime,
) -> None:
    exists = db.scalar(
        select(Cohort.id).where(Cohort.owner_id == researcher.id, Cohort.name == _COHORT)
    )
    if exists is not None:
        return
    manifest = "\n".join(f"{analysis.id},{label}" for _, label, analysis in rows)
    digest = hashlib.sha256(f"analysis_id,label\n{manifest}\n".encode()).hexdigest()
    entries = [
        Entry(ref, label, analysis.probability, analysis.decision) for ref, label, analysis in rows
    ]
    db.add(
        Cohort(
            name=_COHORT,
            source=CohortSource.analyses,
            status=CohortStatus.done,
            owner_id=researcher.id,
            model_version_id=model.id,
            csv_hash=digest,
            results=build_results(model, digest, entries),
            created_at=now,
            finished_at=now,
            items=[
                CohortItem(analysis=analysis, patient_ref=ref, label=label)
                for ref, label, analysis in rows
            ],
        )
    )
