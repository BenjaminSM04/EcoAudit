"""Motor y sesiones de SQLAlchemy."""
from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

if TYPE_CHECKING:
    from .migrate import MigrationReport


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    url = get_settings().database_url
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, **kwargs)


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


def get_db() -> Iterator[Session]:
    db = new_session()
    try:
        yield db
    finally:
        db.close()


def init_db(engine: Engine | None = None) -> MigrationReport:
    """Deja la base en la última revisión de Alembic (ver ``app.migrate``).

    Crea la base si no existe y adopta una anterior a Alembic. ``engine`` permite apuntar a otra
    base, por ejemplo en las pruebas; por defecto es la de la configuración.
    """
    from .migrate import run_migrations

    return run_migrations(engine or get_engine())
