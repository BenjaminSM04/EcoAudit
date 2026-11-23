"""Migraciones de la base de datos (Alembic) y adopción de bases anteriores a Alembic.

``init_db`` llama a ``run_migrations`` en cada arranque de la API, del worker y de la CLI, así que
una base nueva se crea con ``alembic upgrade head`` y una base ya migrada solo avanza si hay
migraciones pendientes.

Adopción de bases preexistentes (mecanismo de un solo uso)
----------------------------------------------------------
Antes de Alembic las tablas se creaban con ``Base.metadata.create_all``, que no altera tablas que
ya existen: cuando un modelo ganaba una columna, las bases viejas quedaban rotas. Esas bases
tienen tablas pero no la tabla ``alembic_version``. Para ellas, ``run_migrations`` hace esto una
sola vez, antes de migrar:

1. Compara con ``inspect()`` lo que hay contra ``Base.metadata``.
2. Crea las tablas que faltan (con sus índices).
3. Agrega las columnas que faltan, solo si es seguro: que admitan NULL o tengan valor por defecto
   del servidor (``ALTER TABLE ... ADD COLUMN``). Si falta una columna obligatoria sin valor por
   defecto, falla con ``AdoptionError`` sin haber tocado nada.
4. Marca la base con la revisión ``ADOPTION_REVISION`` (``alembic stamp``).

Desde ahí la base es una base Alembic normal y este camino ya no vuelve a ejecutarse: lo que
cambie en los modelos se hace con migraciones nuevas, nunca más con ``create_all``.

Límites a tener presentes:

* La adopción sella ``0001`` y excluye los cambios posteriores del esquema de los modelos.
* Solo se detectan tablas y columnas ausentes. No corrige tipos, índices, claves foráneas ni
  columnas que sobran en una tabla existente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import Column, Table, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateColumn

from . import models  # noqa: F401  (registra las tablas en Base.metadata)
from .db import Base

log = logging.getLogger("ecoaudit.db")

# ``alembic.ini`` vive en ``backend/``, junto al paquete ``app``; se ubica sin mirar el directorio
# de trabajo.
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
ADOPTION_REVISION = "0001"
_TABLES_AFTER_ADOPTION = {"clinical_readings", "case_readers"}

# Clave del bloqueo consultivo de PostgreSQL: la API y el worker arrancan a la vez y no deben
# migrar al mismo tiempo.
_LOCK_KEY = 0x45434F41


class AdoptionError(RuntimeError):
    """La base existente no se puede adoptar sin intervención manual."""


@dataclass
class MigrationReport:
    """Qué hizo ``run_migrations``; la CLI lo imprime."""

    revision: str | None = None
    adopted: bool = False
    tables_created: list[str] = field(default_factory=list)
    columns_added: list[str] = field(default_factory=list)  # "tabla.columna"


def _alembic_config(connection: Connection) -> Config:
    if not ALEMBIC_INI.is_file():
        raise FileNotFoundError(
            f"No se encontró {ALEMBIC_INI}. alembic.ini y migrations/ deben estar junto al "
            "paquete app (en Docker, cópielos a la misma carpeta que app/)."
        )
    config = Config(str(ALEMBIC_INI))
    # env.py usa esta conexión y la transacción de quien llama, en vez de abrir otra.
    config.attributes["connection"] = connection
    return config


def _plan_adoption(connection: Connection) -> tuple[list[Table], list[tuple[Table, Column]]]:
    """Calcula qué falta, sin modificar nada. Falla si algo falta y no es seguro agregarlo."""
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    missing_tables: list[Table] = []
    missing_columns: list[tuple[Table, Column]] = []
    blocked: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name in _TABLES_AFTER_ADOPTION:
            continue
        if table.name not in existing:
            missing_tables.append(table)
            continue
        present = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            name = f"{table.name}.{column.name}"
            if column.primary_key or (not column.nullable and column.server_default is None):
                blocked.append(f"{name} (obligatoria y sin valor por defecto)")
            elif column.unique and not column.index:
                # SQLite no permite agregar una restricción UNIQUE con ADD COLUMN.
                blocked.append(f"{name} (con restricción UNIQUE)")
            else:
                missing_columns.append((table, column))

    if blocked:
        raise AdoptionError(
            "No se puede adoptar la base de datos existente: le faltan columnas que no se "
            "pueden agregar con seguridad: "
            + ", ".join(blocked)
            + ". Agréguelas a mano (ALTER TABLE) o migre los datos a una base nueva; "
            "no se modificó nada."
        )
    return missing_tables, missing_columns


def _add_column(connection: Connection, table: Table, column: Column) -> None:
    preparer = connection.dialect.identifier_preparer
    definition = str(CreateColumn(column).compile(dialect=connection.dialect))
    ddl = f"ALTER TABLE {preparer.format_table(table)} ADD COLUMN {definition}"
    for foreign_key in column.foreign_keys:
        target = foreign_key.column
        ddl += f" REFERENCES {preparer.format_table(target.table)} ({preparer.quote(target.name)})"
    connection.execute(text(ddl))


def _adopt(connection: Connection, report: MigrationReport) -> None:
    """Pone al día una base anterior a Alembic. Ver la nota del módulo."""
    missing_tables, missing_columns = _plan_adoption(connection)

    if missing_tables:
        Base.metadata.create_all(connection, tables=missing_tables)
        report.tables_created = [table.name for table in missing_tables]

    added_by_table: dict[Table, set[str]] = {}
    for table, column in missing_columns:
        _add_column(connection, table, column)
        added_by_table.setdefault(table, set()).add(column.name)
        report.columns_added.append(f"{table.name}.{column.name}")
    # Los índices de una tabla nueva ya los creó create_all; faltan los de columnas agregadas.
    for table, names in added_by_table.items():
        for index in table.indexes:
            if names & {column.name for column in index.columns}:
                index.create(connection)

    report.adopted = True
    log.warning(
        "Base sin alembic_version adoptada como %s. Tablas creadas: %s. Columnas agregadas: %s.",
        ADOPTION_REVISION,
        ", ".join(report.tables_created) or "ninguna",
        ", ".join(report.columns_added) or "ninguna",
    )


def run_migrations(engine: Engine) -> MigrationReport:
    """Lleva la base a la última revisión; adopta antes las bases anteriores a Alembic."""
    report = MigrationReport()
    # Una sola transacción: en PostgreSQL, si algo falla no queda nada a medias.
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": _LOCK_KEY})
        config = _alembic_config(connection)
        tables = set(inspect(connection).get_table_names())
        if tables and "alembic_version" not in tables:
            _adopt(connection, report)
            command.stamp(config, ADOPTION_REVISION)
        command.upgrade(config, "head")
        report.revision = MigrationContext.configure(connection).get_current_revision()
    return report
