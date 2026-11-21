"""Cuenta: cambio de contraseña, invalidación de tokens y límite de intentos de login."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, Role, User, utcnow
from app.security import (
    TokenClaims,
    create_access_token,
    hash_password,
    issued_before,
    verify_password,
)

from .conftest import PASSWORD, login, make_user

NEW_PASSWORD = "otra-clave-segura-456"


def _login_raw(client, email: str, password: str):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def _legacy_token(user_id: int, issued_at: int) -> str:
    """Token como los emitidos antes de ``iat_us``: solo ``iat`` en segundos enteros."""
    payload = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": datetime.now(UTC) + timedelta(hours=1),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ cambio de contraseña
def test_change_password_invalidates_old_tokens_but_not_new_ones(client, db):
    make_user(db, "a@test.bo", Role.medico)
    old = login(client, "a@test.bo")
    assert client.get("/api/auth/me", headers=old).status_code == 200

    wrong = client.post(
        "/api/auth/password",
        headers=old,
        json={"current_password": "x" * 12, "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 400
    assert client.get("/api/auth/me", headers=old).status_code == 200  # sin cambios

    changed = client.post(
        "/api/auth/password",
        headers=old,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 204 and changed.content == b""

    # El token emitido antes deja de valer, aunque sea del mismo segundo que el cambio.
    assert client.get("/api/auth/me", headers=old).status_code == 401
    assert _login_raw(client, "a@test.bo", PASSWORD).status_code == 401
    # Uno emitido justo después sigue siendo válido.
    fresh = _login_raw(client, "a@test.bo", NEW_PASSWORD)
    assert fresh.status_code == 200
    assert (
        client.get("/api/auth/me", headers=_bearer(fresh.json()["access_token"])).status_code == 200
    )


def test_change_password_validates_length_and_requires_authentication(client, medico):
    short = client.post(
        "/api/auth/password",
        headers=medico,
        json={"current_password": PASSWORD, "new_password": "corta"},
    )
    assert short.status_code == 422
    assert (
        client.post(
            "/api/auth/password", json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}
        ).status_code
        == 401
    )


def test_change_password_is_audited_and_does_not_affect_other_users(client, db, medico):
    make_user(db, "otro@test.bo", Role.medico)
    other = login(client, "otro@test.bo")
    client.post(
        "/api/auth/password",
        headers=medico,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert client.get("/api/auth/me", headers=other).status_code == 200
    assert "password_changed" in set(db.scalars(select(AuditLog.action)))


def test_long_passwords_beyond_bcrypt_limit_work_and_are_not_truncated(client, db):
    make_user(db, "a@test.bo", Role.medico)
    headers = login(client, "a@test.bo")
    long_password = "a" * 100
    assert verify_password(long_password, hash_password(long_password))
    assert not verify_password("a" * 72, hash_password(long_password))

    response = client.post(
        "/api/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": long_password},
    )
    assert response.status_code == 204
    assert _login_raw(client, "a@test.bo", long_password).status_code == 200
    assert _login_raw(client, "a@test.bo", "a" * 72).status_code == 401


# ------------------------------------------------------------------ restablecimiento por admin
def test_admin_resets_password_and_revokes_tokens(client, db, admin, medico):
    target = db.scalar(select(User).where(User.email == "medico@test.bo"))
    assert client.get("/api/auth/me", headers=medico).status_code == 200

    response = client.post(
        f"/api/users/{target.id}/password", headers=admin, json={"new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert client.get("/api/auth/me", headers=medico).status_code == 401
    assert _login_raw(client, "medico@test.bo", PASSWORD).status_code == 401
    assert _login_raw(client, "medico@test.bo", NEW_PASSWORD).status_code == 200
    assert client.get("/api/auth/me", headers=admin).status_code == 200  # el admin no se afecta
    assert "password_reset" in set(db.scalars(select(AuditLog.action)))


def test_reset_password_is_admin_only_and_validates(client, db, admin, medico, investigador):
    target = db.scalar(select(User).where(User.email == "medico@test.bo"))
    body = {"new_password": NEW_PASSWORD}
    assert (
        client.post(f"/api/users/{target.id}/password", headers=medico, json=body).status_code
        == 403
    )
    assert (
        client.post(f"/api/users/{target.id}/password", headers=investigador, json=body).status_code
        == 403
    )
    assert client.post("/api/users/9999/password", headers=admin, json=body).status_code == 404
    assert (
        client.post(
            f"/api/users/{target.id}/password", headers=admin, json={"new_password": "corta"}
        ).status_code
        == 422
    )


# ------------------------------------------------------------------ precisión del iat
def test_issued_before_is_exact_with_microseconds():
    changed = datetime(2026, 5, 1, 12, 0, 0, 500_000, tzinfo=UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    us = (changed - epoch) // timedelta(microseconds=1)
    iat = us // 1_000_000
    assert issued_before(TokenClaims(1, iat, us - 1), changed)  # justo antes: inválido
    assert not issued_before(TokenClaims(1, iat, us), changed)
    assert not issued_before(TokenClaims(1, iat, us + 1), changed)  # justo después: válido


def test_issued_before_without_microseconds_never_rejects_a_later_token():
    changed = datetime(2026, 5, 1, 12, 0, 0, 900_000, tzinfo=UTC)
    second = int(changed.timestamp())
    # Un token antiguo emitido a las 12:00:00,950 trae iat = 12:00:00, igual que el segundo del
    # cambio: no se puede rechazar sin riesgo de invalidar uno emitido justo después.
    assert not issued_before(TokenClaims(1, second, None), changed)
    assert issued_before(TokenClaims(1, second - 1, None), changed)


def test_legacy_token_without_microseconds_is_checked_by_whole_second(client, db):
    user = make_user(db, "a@test.bo", Role.medico)
    changed = utcnow()
    user.password_changed_at = changed
    db.commit()
    second = int(changed.timestamp())

    assert (
        client.get("/api/auth/me", headers=_bearer(_legacy_token(user.id, second))).status_code
        == 200
    )
    assert (
        client.get("/api/auth/me", headers=_bearer(_legacy_token(user.id, second - 5))).status_code
        == 401
    )


def test_fresh_token_carries_microsecond_claim():
    claims = jwt.decode(create_access_token(7), get_settings().secret_key, algorithms=["HS256"])
    assert claims["iat_us"] // 1_000_000 == claims["iat"]


# ------------------------------------------------------------------ límite de intentos
def _failed_events(db, email: str) -> list[AuditLog]:
    return [
        e
        for e in db.scalars(select(AuditLog).where(AuditLog.action == "login_failed"))
        if e.detail.get("email") == email
    ]


def test_five_failures_block_the_email_even_with_the_right_password(client, db):
    make_user(db, "a@test.bo", Role.medico)
    for _ in range(5):
        assert _login_raw(client, "a@test.bo", "x" * 12).status_code == 401

    blocked = _login_raw(client, "a@test.bo", PASSWORD)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Demasiados intentos fallidos. Espere 15 minutos."
    # También con otra grafía del mismo correo; otro correo no se ve afectado.
    assert _login_raw(client, "  A@Test.BO ", PASSWORD).status_code == 429
    make_user(db, "b@test.bo", Role.medico)
    assert _login_raw(client, "b@test.bo", PASSWORD).status_code == 200
    # Los intentos bloqueados no suman: el bloqueo no se alarga mientras se insiste.
    assert len(_failed_events(db, "a@test.bo")) == 5


def test_four_failures_do_not_block(client, db):
    make_user(db, "a@test.bo", Role.medico)
    for _ in range(4):
        _login_raw(client, "a@test.bo", "x" * 12)
    assert _login_raw(client, "a@test.bo", PASSWORD).status_code == 200


def test_failures_are_stored_with_the_normalized_email_and_old_ones_expire(client, db):
    make_user(db, "a@test.bo", Role.medico)
    for _ in range(5):
        _login_raw(client, "  A@Test.BO ", "x" * 12)
    events = _failed_events(db, "a@test.bo")
    assert len(events) == 5
    assert _login_raw(client, "a@test.bo", PASSWORD).status_code == 429

    for event in events:
        event.created_at = utcnow() - timedelta(minutes=16)
    db.commit()
    assert _login_raw(client, "a@test.bo", PASSWORD).status_code == 200


def test_unknown_emails_are_throttled_too(client):
    for _ in range(5):
        assert _login_raw(client, "nadie@test.bo", "x" * 12).status_code == 401
    assert _login_raw(client, "nadie@test.bo", "x" * 12).status_code == 429
