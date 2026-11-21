"""Contraseñas (bcrypt) y tokens de acceso (JWT HS256)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from .config import get_settings

_ALGORITHM = "HS256"
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_BCRYPT_MAX_BYTES = 72


def _bcrypt_input(password: str) -> bytes:
    """bcrypt solo admite 72 bytes (y la versión 5 lanza error si se superan). Las contraseñas
    más largas se reducen antes a su SHA-256 en hexadecimal; las demás quedan como estaban."""
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return hashlib.sha256(raw).hexdigest().encode("ascii")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def _microseconds(moment: datetime) -> int:
    """Microsegundos desde la época, con aritmética entera (sin errores de coma flotante)."""
    return (moment - _EPOCH) // timedelta(microseconds=1)


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    issued_at: int  # ``iat`` estándar: segundos enteros, truncados
    issued_at_us: int | None  # ``iat_us`` propio: microsegundos; None en tokens antiguos


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        # ``iat`` pierde la fracción de segundo. Este reclamo la conserva para poder distinguir
        # un token emitido justo antes de un cambio de contraseña de uno emitido justo después.
        "iat_us": _microseconds(now),
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def read_access_token(token: str) -> TokenClaims | None:
    """Valida la firma y la expiración. None si el token es inválido o expiró."""
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[_ALGORITHM])
        precise = payload.get("iat_us")
        return TokenClaims(
            user_id=int(payload["sub"]),
            issued_at=int(payload["iat"]),
            issued_at_us=int(precise) if precise is not None else None,
        )
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


def decode_access_token(token: str) -> int | None:
    """Devuelve el id de usuario, o None si el token es inválido o expiró."""
    claims = read_access_token(token)
    return claims.user_id if claims else None


def issued_before(claims: TokenClaims, moment: datetime) -> bool:
    """True si el token se emitió antes de ``moment`` (p. ej. el último cambio de contraseña).

    Con ``iat_us`` la comparación es exacta: un token emitido justo después del cambio sigue
    siendo válido y uno emitido justo antes deja de serlo. Un token sin él solo trae ``iat`` en
    segundos enteros; se compara con el segundo entero de ``moment`` y solo se rechazan los
    emitidos en un segundo anterior, de modo que nunca se invalide un token posterior al cambio.
    """
    if claims.issued_at_us is not None:
        return claims.issued_at_us < _microseconds(moment)
    return claims.issued_at < _microseconds(moment) // 1_000_000
