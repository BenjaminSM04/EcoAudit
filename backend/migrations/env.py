"""Entorno de Alembic.

Hay dos formas de llegar aquí:

* Programática (``app.migrate.run_migrations``, que usa ``init_db``): el llamador entrega su
  propia conexión en ``config.attributes["connection"]`` y es dueño de la transacción.
* Línea de comandos (``alembic upgrade head``): se abre una conexión con la URL de
  ``get_settings().database_url`` (``ECOAUDIT_DATABASE_URL``), igual que la API.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from app import models  # noqa: F401  (registra las tablas en Base.metadata)
from app.config import get_settings
from app.db import Base, get_engine

config = context.config
target_metadata = Base.metadata


def _configure(**kwargs) -> None:
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        **kwargs,
    )


def _run(connection: Connection) -> None:
    _configure(
        connection=connection,
        # SQLite casi no soporta ALTER: con batch, Alembic reconstruye la tabla cuando hace falta.
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse (``alembic upgrade head --sql``)."""
    url = get_settings().database_url
    _configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    # Desde la línea de comandos: configura el log del .ini sin silenciar a los demás.
    if config.config_file_name is not None:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    with get_engine().begin() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
