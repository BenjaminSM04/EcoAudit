from datetime import timedelta
from io import StringIO

import pytest
from sqlalchemy import func, select

from app import cli
from app.models import (
    Analysis,
    AnalysisStatus,
    Case,
    CaseReader,
    ClinicalReading,
    Cohort,
    CohortStatus,
    Image,
    ModelVersion,
    Role,
    User,
    utcnow,
)
from app.registry import get_active
from app.security import verify_password
from app.storage import get_storage

from .conftest import PASSWORD, make_user


@pytest.mark.parametrize("terminador", ["\n", "\r\n"])
def test_cli_quita_el_fin_de_linea_de_stdin(db, monkeypatch, terminador):
    email = "stdin@ecoaudit.test"
    args = ["create-user", "--email", email, "--name", "Ensayo", "--role", "medico"]
    monkeypatch.setattr("sys.stdin", StringIO(f"123456789{terminador}"))
    assert cli.main(args) == 1
    password = "  contraseña válida  "
    monkeypatch.setattr("sys.stdin", StringIO(f"{password}{terminador}"))
    assert cli.main(args) == 0
    user = db.scalar(select(User).where(User.email == email))
    assert verify_password(password, user.password_hash)


def test_seed_demo_is_idempotent_and_keeps_existing_accounts(db, capsys):
    existing = make_user(db, "medico1@ecoaudit.test", Role.medico)
    command = ["seed-demo", "--password", "demo-clave-987"]
    assert cli.main(command) == 0
    assert "Casos nuevos: 20" in capsys.readouterr().out
    model = get_active(db)
    assert model.card["demo"] is True
    db.refresh(existing)
    assert verify_password(PASSWORD, existing.password_hash)
    assert verify_password(
        command[-1], db.scalar(select(User).where(User.role == Role.admin)).password_hash
    )
    cases = list(db.scalars(select(Case).order_by(Case.id)))
    assert [case.patient_ref for case in cases] == [f"PAC-{9100 + i:04}" for i in range(20)]
    assert [len(case.images) for case in cases] == [1 + i % 3 for i in range(20)]
    images = list(db.scalars(select(Image)))
    assert get_storage().get_bytes(images[0].storage_key).startswith(b"\x89PNG")
    assert len({image.pixel_sha256 for image in images}) == len(images)
    for analysis in db.scalars(select(Analysis)):
        assert utcnow() - timedelta(days=30) < analysis.created_at < analysis.started_at
        assert analysis.started_at < analysis.finished_at < utcnow()
        assert analysis.status == AnalysisStatus.done
        assert analysis.probability is not None and analysis.model_version_id == model.id
    readings = list(db.scalars(select(ClinicalReading)))
    assert {reading.blinded for reading in readings} == {True, False}
    assert len({reading.reader_id for reading in readings}) == 2
    cohort = db.scalars(select(Cohort)).one()
    assert cohort.status == CohortStatus.done and cohort.owner.role == Role.investigador
    assert cohort.results["auc"] is not None and len(cohort.items) > 1
    tables = (User, Case, Image, Analysis, ClinicalReading, CaseReader, Cohort, ModelVersion)

    def counts():
        return [db.scalar(select(func.count()).select_from(table)) for table in tables]

    before = counts()
    assert before[0] == 4
    assert cli.main(command) == 0
    assert "Casos nuevos: 0" in capsys.readouterr().out
    assert counts() == before


def test_seed_demo_keeps_existing_active_model(db, active_model):
    active_model.card = {**active_model.card, "demo": False}
    active_model.bundle_sha256 = "a" * 64
    db.commit()
    assert cli.main(["seed-demo", "--password", PASSWORD]) == 0
    assert get_active(db).id == active_model.id
    demo = db.scalar(select(ModelVersion).where(ModelVersion.id != active_model.id))
    assert demo.card["demo"] and not demo.is_active
    assert set(db.scalars(select(Analysis.model_version_id))) == {demo.id}
