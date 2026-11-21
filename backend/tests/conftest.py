from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

# La configuración se fija antes de importar la aplicación.
_TMP = Path(tempfile.mkdtemp(prefix="ecoaudit-tests-"))
os.environ["ECOAUDIT_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ECOAUDIT_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["ECOAUDIT_INLINE_WORKER"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app import worker  # noqa: E402
from app.db import Base, get_engine, init_db, new_session  # noqa: E402
from app.devtools import make_demo_bundle  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.registry import register_bundle  # noqa: E402
from app.security import hash_password  # noqa: E402

PASSWORD = "clave-de-prueba-123"


@pytest.fixture(autouse=True)
def clean_db():
    engine = get_engine()
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        connection.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    init_db(engine)
    worker._bundles.clear()
    yield


@pytest.fixture
def db():
    session = new_session()
    yield session
    session.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def demo_bundle_dir(tmp_path_factory) -> Path:
    return make_demo_bundle(tmp_path_factory.mktemp("bundle"))


@pytest.fixture
def active_model(db, demo_bundle_dir):
    model = register_bundle(db, demo_bundle_dir, activate=True)
    db.commit()
    return model


def make_user(db, email: str, role: Role) -> User:
    user = User(email=email, full_name=email, password_hash=hash_password(PASSWORD), role=role)
    db.add(user)
    db.commit()
    return user


def login(client, email: str) -> dict[str, str]:
    response = client.post("/api/auth/login", data={"username": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def medico(client, db) -> dict[str, str]:
    make_user(db, "medico@test.bo", Role.medico)
    return login(client, "medico@test.bo")


@pytest.fixture
def investigador(client, db) -> dict[str, str]:
    make_user(db, "investigador@test.bo", Role.investigador)
    return login(client, "investigador@test.bo")


@pytest.fixture
def admin(client, db) -> dict[str, str]:
    make_user(db, "admin@test.bo", Role.admin)
    return login(client, "admin@test.bo")


def noise_pixels(seed: int = 0, size: int = 256) -> np.ndarray:
    rng = np.random.default_rng(seed)
    gray = np.clip(rng.normal(110, 45, size=(size, size)), 0, 255).astype(np.uint8)
    return gray


def png_bytes(pixels: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    Image.fromarray(pixels).save(buffer, format="PNG")
    return buffer.getvalue()
