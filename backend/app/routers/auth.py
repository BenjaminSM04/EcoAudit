from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, record
from ..models import AuditLog, User, utcnow
from ..schemas import PasswordChange, Token, UserOut
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Límite de intentos: 5 fallos para el mismo correo en 15 minutos bloquean el acceso, incluso
# con la contraseña correcta. Se cuenta desde la bitácora (evento ``login_failed`` con el correo
# normalizado en ``detail``), así vale con varios procesos y no necesita tablas nuevas.
MAX_LOGIN_FAILURES = 5
LOGIN_WINDOW = timedelta(minutes=15)


def _recent_failures(db: Session, email: str) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                AuditLog.action == "login_failed",
                AuditLog.created_at >= utcnow() - LOGIN_WINDOW,
                AuditLog.detail["email"].as_string() == email,
            )
        )
        or 0
    )


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    email = form.username.strip().lower()
    if _recent_failures(db, email) >= MAX_LOGIN_FAILURES:
        # El intento bloqueado no suma como fallo: el bloqueo no se prolonga mientras se insiste.
        record(db, None, "login_blocked", "user", email=email)
        db.commit()
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos fallidos. Espere 15 minutos."
        )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        record(db, None, "login_failed", "user", user.id if user else None, email=email)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")
    record(db, user, "login", "user", user.id)
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Response:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual es incorrecta.")
    user.password_hash = hash_password(body.new_password)
    user.password_changed_at = utcnow()  # invalida los tokens emitidos hasta ahora
    record(db, user, "password_changed", "user", user.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
