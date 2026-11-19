"""Migraciones con Alembic y adopción de bases anteriores.

Estas pruebas usan bases SQLite propias en archivos temporales; no tocan la base de las demás
pruebas (que la crea ``conftest`` con ``create_all``).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.orm import Session

from app import cli, migrate
from app.db import Base, init_db
from app.migrate import ADOPTION_REVISION, AdoptionError
from app.models import Analysis, AnalysisStatus, Role, User, utcnow


@pytest.fixture
def engine(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'migrada.db').as_posix()}")
    yield eng
    eng.dispose()


def _schema(connection) -> dict[str, set[str]]:
    inspector = inspect(connection)
    return {
        table: {col["name"] for col in inspector.get_columns(table)}
        for table in inspector.get_table_names()
        if table != "alembic_version"
    }


def _expected_schema() -> dict[str, set[str]]:
    return {
        table.name: {col.name for col in table.columns}
        for table in Base.metadata.tables.values()
    }


def _revision(connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _legacy_database(engine) -> None:
    """Reproduce la base de desarrollo anterior a Alembic: sin ``users.password_changed_at``,
    ``analyses.attempts``, ``cohorts`` ni ``cohort_items``, y con datos."""
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE cohort_items"))
        connection.execute(text("DROP TABLE cohorts"))
        connection.execute(text("ALTER TABLE users DROP COLUMN password_changed_at"))
        connection.execute(text("ALTER TABLE analyses DROP COLUMN attempts"))
        connection.execute(
            text(
                "INSERT INTO users (id, email, full_name, password_hash, role, is_active, "
                "created_at) VALUES (1, 'viejo@test.bo', 'Viejo', 'x', 'medico', 1, "
                "'2026-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO analyses (id, image_id, requested_by_id, model_version_id, status, "
                "warnings, created_at) VALUES (7, 1, 1, 1, 'pending', '[]', "
                "'2026-01-01 00:00:00')"
            )
        )


def test_migrations_on_empty_database_match_the_models(engine):
    report = init_db(engine)

    assert report.revision == ADOPTION_REVISION and not report.adopted
    with engine.connect() as connection:
        assert _revision(connection) == ADOPTION_REVISION
        assert _schema(connection) == _expected_schema()
        # Tipos, nulabilidad, índices y claves: nada que Alembic detecte como distinto.
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_running_migrations_twice_changes_nothing(engine):
    init_db(engine)
    report = init_db(engine)
    assert not report.adopted and report.revision == ADOPTION_REVISION


def test_old_database_is_adopted_and_usable(engine):
    _legacy_database(engine)
    with engine.connect() as connection:
        assert _revision(connection) is None
        assert "attempts" not in _schema(connection)["analyses"]
        assert "password_changed_at" not in _schema(connection)["users"]

    report = init_db(engine)

    assert report.adopted and report.revision == ADOPTION_REVISION
    assert sorted(report.tables_created) == ["cohort_items", "cohorts"]
    assert sorted(report.columns_added) == ["analyses.attempts", "users.password_changed_at"]
    with engine.connect() as connection:
        assert _revision(connection) == ADOPTION_REVISION  # marcada
        assert _schema(connection) == _expected_schema()
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []

    with Session(engine) as session:
        # Los datos previos siguen y las columnas nuevas tienen su valor inicial.
        user = session.scalars(select(User)).one()
        assert user.email == "viejo@test.bo" and user.password_changed_at is None
        analysis = session.get(Analysis, 7)
        assert analysis.attempts == 0 and analysis.status == AnalysisStatus.pending
        # Y se puede escribir con el modelo actual.
        analysis.attempts += 1
        session.add(
            User(email="nuevo@test.bo", full_name="Nuevo", password_hash="x", role=Role.admin,
                 password_changed_at=utcnow())
        )
        session.commit()
        assert session.get(Analysis, 7).attempts == 1

    # Ya sellada: arrancar otra vez no vuelve a adoptar.
    assert not init_db(engine).adopted


def test_adoption_adds_columns_with_index_default_and_foreign_key(engine, monkeypatch):
    # Los modelos reales no tienen una columna opcional con índice; se usa un esquema de juguete.
    metadata = MetaData()
    Table("padre", metadata, Column("id", Integer, primary_key=True))
    Table(
        "cosa",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("etiqueta", String(10), nullable=True, index=True),
        Column("nivel", Integer, nullable=False, server_default="3"),
        Column("padre_id", Integer, ForeignKey("padre.id"), nullable=True),
    )
    monkeypatch.setattr(migrate, "Base", SimpleNamespace(metadata=metadata))
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE padre (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE cosa (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO cosa (id) VALUES (1)"))

    report = migrate.run_migrations(engine)

    assert sorted(report.columns_added) == ["cosa.etiqueta", "cosa.nivel", "cosa.padre_id"]
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert [i["name"] for i in inspector.get_indexes("cosa")] == ["ix_cosa_etiqueta"]
        assert inspector.get_foreign_keys("cosa")[0]["referred_table"] == "padre"
        assert connection.execute(text("SELECT nivel FROM cosa")).scalar_one() == 3
        assert _revision(connection) == ADOPTION_REVISION


def test_adoption_fails_clearly_when_a_required_column_has_no_default(engine):
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255) NOT NULL)")
        )

    with pytest.raises(AdoptionError) as error:
        init_db(engine)

    message = str(error.value)
    assert "users.full_name" in message and "obligatoria" in message
    assert "no se modificó nada" in message
    # No quedó nada a medias: ni tablas nuevas ni sello.
    with engine.connect() as connection:
        assert inspect(connection).get_table_names() == ["users"]


def test_cli_db_upgrade_reports_the_revision(capsys):
    # Apunta a la base de pruebas (la fija conftest con ECOAUDIT_DATABASE_URL).
    assert cli.main(["db-upgrade"]) == 0
    assert f"revisión {ADOPTION_REVISION}" in capsys.readouterr().out
