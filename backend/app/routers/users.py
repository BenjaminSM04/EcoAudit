from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import record, require_roles
from ..models import Role, User, utcnow
from ..schemas import PasswordReset, UserCreate, UserOut, UserUpdate
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])
_admin = require_roles(Role.admin)


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(_admin)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.id)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(_admin)
) -> User:
    email = body.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese correo.")
    user = User(
        email=email,
        full_name=body.full_name.strip(),
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.flush()
    record(db, admin, "user_created", "user", user.id, role=body.role.value)
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(_admin)
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    if user.id == admin.id and (body.is_active is False or body.role not in (None, Role.admin)):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No puede desactivarse ni quitarse el rol de administrador.",
        )
    changes = body.model_dump(exclude_none=True)
    for key, value in changes.items():
        setattr(user, key, value)
    record(db, admin, "user_updated", "user", user.id, **{k: str(v) for k, v in changes.items()})
    db.commit()
    return user


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    user_id: int,
    body: PasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(_admin),
) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado.")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()  # invalida los tokens de ese usuario
    record(db, admin, "password_reset", "user", user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
