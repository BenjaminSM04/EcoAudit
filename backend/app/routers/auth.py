from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user, record
from ..models import User
from ..schemas import Token, UserOut
from ..security import create_access_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        record(db, None, "login_failed", "user", user.id if user else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")
    record(db, user, "login", "user", user.id)
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
