"""Dependencias de FastAPI: usuario autenticado, control de roles y bitácora."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditLog, Role, User
from .security import decode_access_token

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(_oauth2), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sesión inválida o expirada.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: Role) -> Callable[[User], User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Su rol no permite esta acción.")
        return user

    return dependency


def record(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    **detail: object,
) -> AuditLog:
    """Agrega una entrada a la bitácora. El commit lo hace quien llama."""
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    )
    db.add(entry)
    return entry
