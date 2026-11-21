"""Registro de modelos: alta de bundles y selección del modelo activo."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .models import ModelVersion
from .pipeline.bundle import BundleError, ModelBundle, bundle_sha256
from .storage import get_storage


def register_bundle(db: Session, directory: Path, activate: bool = False) -> ModelVersion:
    """Valida el bundle, lo copia al almacén y lo registra. Es idempotente por hash."""
    directory = Path(directory)
    if not directory.is_dir():
        raise BundleError(f"No existe el directorio {directory}.")
    bundle = ModelBundle(directory)
    bundle.self_check()

    digest = bundle_sha256(directory)
    existing = db.scalar(select(ModelVersion).where(ModelVersion.bundle_sha256 == digest))
    if existing is None:
        storage_key = f"models/{digest[:16]}"
        get_storage().put_dir(storage_key, directory)
        existing = ModelVersion(
            name=bundle.card["name"],
            version=bundle.card["version"],
            bundle_sha256=digest,
            storage_key=storage_key,
            card=bundle.card,
        )
        db.add(existing)
        db.flush()
    if activate:
        set_active(db, existing)
    return existing


def set_active(db: Session, model: ModelVersion) -> None:
    db.execute(update(ModelVersion).values(is_active=False))
    model.is_active = True
    db.flush()


def get_active(db: Session) -> ModelVersion | None:
    return db.scalar(select(ModelVersion).where(ModelVersion.is_active.is_(True)))
