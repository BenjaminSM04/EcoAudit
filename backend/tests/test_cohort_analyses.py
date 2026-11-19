"""Cohorte desde análisis existentes (CSV), acceso por dueño, informe y tabla."""
from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import func, select

from app import worker
from app.devtools import make_demo_bundle
from app.models import AuditLog, Cohort, Role
from app.registry import register_bundle

from .conftest import login, make_user, noise_pixels, png_bytes


def _done_analysis(client, db, headers, patient_ref: str, seed: int) -> int:
    """Caso con una imagen y su análisis ya terminado por el worker."""
    case_id = client.post("/api/cases", headers=headers, json={"patient_ref": patient_ref}).json()[
        "id"
    ]
    image_id = client.post(
        f"/api/cases/{case_id}/images",
        headers=headers,
        files={"file": ("eco.png", png_bytes(noise_pixels(seed)), "image/png")},
    ).json()["id"]
    analysis_id = client.post(f"/api/images/{image_id}/analyses", headers=headers, json={}).json()[
        "id"
    ]
    assert worker.process_analysis(db, analysis_id)
    return analysis_id


def _csv(*rows: tuple[int, int]) -> bytes:
    return ("analysis_id,label\n" + "".join(f"{a},{label}\n" for a, label in rows)).encode()


def _post_csv(client, headers, content: bytes, **data):
    return client.post(
        "/api/cohorts", headers=headers, data=data, files={"file": ("c.csv", content)}
    )


@pytest.fixture
def two_analyses(client, db, investigador, active_model):
    return (
        _done_analysis(client, db, investigador, "P-1", seed=1),
        _done_analysis(client, db, investigador, "P-2", seed=2),
    )


def test_cohort_from_own_analyses(client, db, investigador, two_analyses):
    first, second = two_analyses
    response = _post_csv(client, investigador, _csv((first, 1), (second, 0)), name="  Mi cohorte ")
    assert response.status_code == 201, response.text
    cohort = response.json()

    assert cohort["status"] == "done" and cohort["source"] == "analyses"
    assert cohort["name"] == "Mi cohorte" and cohort["error"] is None
    assert cohort["model"] == "demo-brillo 0.0.0"
    assert cohort["progress"] == {"total": 2, "done": 2, "failed": 0}
    results = cohort["results"]
    assert results["patients"] == 2 and results["positive"] == 1 and results["images"] == 2
    assert 0.0 <= results["auc"] <= 1.0 and results["ci"] is None
    assert sum(results["decisions"].values()) == 2
    assert results["demo"] is True and len(results["model_hash"]) == 64
    assert len(results["csv_hash"]) == 64
    assert sum(b["n"] for b in results["bins"]) == 2

    # Lo que devuelve el POST es lo que luego da el GET. En la bitácora solo queda el alta.
    assert client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json() == cohort
    entries = db.scalars(select(AuditLog).where(AuditLog.entity == "cohort")).all()
    assert [(e.action, e.entity_id) for e in entries] == [("cohort_created", cohort["id"])]
    assert entries[0].detail == {}


def test_cohort_name_is_optional_and_limited(client, investigador, two_analyses):
    first, second = two_analyses
    unnamed = _post_csv(client, investigador, _csv((first, 1), (second, 0)))
    assert unnamed.status_code == 201 and unnamed.json()["name"].startswith("Cohorte ")
    too_long = _post_csv(client, investigador, _csv((first, 1), (second, 0)), name="x" * 121)
    assert too_long.status_code == 422


def test_cohort_rejects_analyses_of_other_users_without_revealing_them(
    client, db, investigador, admin, two_analyses
):
    first, _ = two_analyses
    make_user(db, "otro@test.bo", Role.investigador)
    other = login(client, "otro@test.bo")
    mine = _done_analysis(client, db, other, "Q-1", seed=3)

    foreign = _post_csv(client, other, _csv((mine, 1), (first, 0)))
    missing = _post_csv(client, other, _csv((mine, 1), (999999, 0)))
    assert foreign.status_code == 422 and missing.status_code == 422
    # La misma respuesta si el análisis es ajeno o no existe, con el número de fila.
    assert foreign.json()["detail"] == missing.json()["detail"]
    assert "fila 3" in foreign.json()["detail"]
    assert db.scalar(select(func.count()).select_from(Cohort)) == 0

    # El administrador sí puede auditar análisis de varios usuarios.
    allowed = _post_csv(client, admin, _csv((mine, 1), (first, 0)))
    assert allowed.status_code == 201, allowed.text


def test_cohort_requires_finished_analyses_and_one_model_version(
    client, db, investigador, two_analyses, tmp_path
):
    first, _ = two_analyses
    case_id = client.post("/api/cases", headers=investigador, json={"patient_ref": "P-3"}).json()[
        "id"
    ]
    image_id = client.post(
        f"/api/cases/{case_id}/images",
        headers=investigador,
        files={"file": ("eco.png", png_bytes(noise_pixels(9)), "image/png")},
    ).json()["id"]
    pending = client.post(
        f"/api/images/{image_id}/analyses", headers=investigador, json={}
    ).json()["id"]
    assert _post_csv(client, investigador, _csv((first, 1), (pending, 0))).status_code == 422

    register_bundle(db, make_demo_bundle(tmp_path / "otro", seed=1), activate=True)
    db.commit()
    newer = _done_analysis(client, db, investigador, "P-4", seed=10)
    mixed = _post_csv(client, investigador, _csv((first, 1), (newer, 0)))
    assert mixed.status_code == 422 and "versión de modelo" in mixed.json()["detail"]


def test_cohort_rejects_single_class_and_repeated_images(client, investigador, two_analyses):
    first, second = two_analyses
    assert _post_csv(client, investigador, _csv((first, 1), (second, 1))).status_code == 422
    repeated = _post_csv(client, investigador, _csv((first, 1), (first, 1), (second, 0)))
    assert repeated.status_code == 422


def test_cohort_access_is_per_owner(client, db, investigador, admin, medico, two_analyses):
    first, second = two_analyses
    cohort_id = _post_csv(client, investigador, _csv((first, 1), (second, 0))).json()["id"]
    make_user(db, "otro@test.bo", Role.investigador)
    other = login(client, "otro@test.bo")

    assert [c["id"] for c in client.get("/api/cohorts", headers=investigador).json()] == [cohort_id]
    assert client.get("/api/cohorts", headers=other).json() == []
    for suffix in ("", "/report", "/items.csv"):
        url = f"/api/cohorts/{cohort_id}{suffix}"
        assert client.get(url, headers=other).status_code == 404, url
        assert client.get(url, headers=admin).status_code == 200, url
        assert client.get(url, headers=investigador).status_code == 200, url
        assert client.get(url, headers=medico).status_code == 403, url
    assert client.get("/api/cohorts/9999", headers=investigador).status_code == 404
    assert client.get("/api/cohorts", headers=medico).status_code == 403
    assert [c["id"] for c in client.get("/api/cohorts", headers=admin).json()] == [cohort_id]


def test_cohort_list_is_newest_first_with_summary_fields(client, investigador, two_analyses):
    first, second = two_analyses
    older = _post_csv(client, investigador, _csv((first, 1), (second, 0)), name="Vieja").json()
    newer = _post_csv(client, investigador, _csv((first, 0), (second, 1)), name="Nueva").json()
    listing = client.get("/api/cohorts", headers=investigador).json()
    assert [c["id"] for c in listing] == [newer["id"], older["id"]]
    assert set(listing[0]) == {"id", "name", "source", "status", "model", "created_at", "progress"}


def test_cohort_report_and_items_csv(client, investigador, two_analyses):
    first, second = two_analyses
    cohort = _post_csv(client, investigador, _csv((first, 1), (second, 0))).json()

    report = client.get(f"/api/cohorts/{cohort['id']}/report", headers=investigador)
    assert report.status_code == 200
    assert report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF")

    response = client.get(f"/api/cohorts/{cohort['id']}/items.csv", headers=investigador)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["analysis_id", "patient_ref", "label", "probability", "decision", "status"]
    assert [r[:3] for r in rows[1:]] == [[str(first), "P-1", "1"], [str(second), "P-2", "0"]]
    assert all(r[5] == "done" and 0 < float(r[3]) < 1 and r[4] for r in rows[1:])
