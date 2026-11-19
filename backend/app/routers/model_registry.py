from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, record, require_roles
from ..models import ModelVersion, Role, User
from ..registry import set_active
from ..schemas import ModelVersionOut

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelVersionOut])
def list_models(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
) -> list[ModelVersion]:
    return list(db.scalars(select(ModelVersion).order_by(ModelVersion.id.desc())))


@router.post("/{model_id}/activate", response_model=ModelVersionOut)
def activate_model(
    model_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(Role.admin)),
) -> ModelVersion:
    model = db.get(ModelVersion, model_id)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo no encontrado.")
    set_active(db, model)
    record(db, admin, "model_activated", "model_version", model.id, sha256=model.bundle_sha256)
    db.commit()
    return model
