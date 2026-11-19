"""Cohorte desde un lote nuevo de imágenes: ``POST /api/cohorts/batch``."""
from __future__ import annotations

import csv
import io
import shutil
from datetime import timedelta

import numpy as np
import pytest
from sqlalchemy import func, select

from app import worker
from app.config import get_settings
from app.models import Analysis, AuditLog, Case, Cohort, CohortItem, Image, Role, utcnow
from app.storage import Storage, get_storage

from .conftest import login, make_user, noise_pixels, png_bytes


@pytest.fixture(autouse=True)
def clean_images_dir():
    """El almacén es común a toda la sesión de pruebas y los ids reinician con cada base nueva:
    se vacía ``images/`` para comparar qué archivos escribe (o no) cada prueba."""
    shutil.rmtree(get_storage().root / "images", ignore_errors=True)
    yield


# (archivo, paciente, etiqueta, semilla de la imagen)
BATCH = [
    ("a1.png", "P-A", 1, 1),
    ("a2.png", "P-A", 1, 2),
    ("b1.png", "P-B", 1, 3),
    ("c1.png", "P-C", 0, 4),
    ("d1.png", "P-D", 0, 5),
]


def _manifest(rows=BATCH, header: str = "filename,patient_ref,label") -> bytes:
    return (header + "\n" + "".join(f"{f},{p},{label}\n" for f, p, label, _ in rows)).encode()


def _files(rows=BATCH, manifest: bytes | None = None) -> list:
    files = [("manifest", ("manifest.csv", manifest or _manifest(rows), "text/csv"))]
    files += [("images", (name, png_bytes(noise_pixels(seed)), "image/png")) for name, _, _, seed in rows]
    return files


def _post_batch(client, headers, files=None, name: str | None = "Lote de prueba"):
    return client.post(
        "/api/cohorts/batch",
        headers=headers,
        data={} if name is None else {"name": name},
        files=files if files is not None else _files(),
    )


def _counts(db) -> dict[str, int]:
    return {
        model.__name__: db.scalar(select(func.count()).select_from(model))
        for model in (Case, Image, Analysis, Cohort, CohortItem)
    }


def _stored_images() -> set:
    root = get_storage().root / "images"
    return {p for p in root.rglob("*") if p.is_file()} if root.exists() else set()


def _drain(db) -> int:
    processed = 0
    while worker.process_next(db):
        processed += 1
    return processed


# ------------------------------------------------------------------ de punta a punta
def test_batch_end_to_end(client, db, investigador, active_model):
    response = _post_batch(client, investigador)
    assert response.status_code == 201, response.text
    cohort = response.json()
    assert cohort["status"] == "processing" and cohort["source"] == "batch"
    assert cohort["name"] == "Lote de prueba" and cohort["model"] == "demo-brillo 0.0.0"
    assert cohort["progress"] == {"total": 5, "done": 0, "failed": 0}
    assert cohort["results"] is None and cohort["error"] is None

    # Un caso por paciente, del usuario; las imágenes ya cargadas y un análisis pendiente por imagen.
    cases = client.get("/api/cases", headers=investigador).json()
    assert sorted((c["patient_ref"], c["image_count"]) for c in cases) == [
        ("P-A", 2), ("P-B", 1), ("P-C", 1), ("P-D", 1),
    ]
    analyses = list(db.scalars(select(Analysis).order_by(Analysis.id)))
    assert len(analyses) == 5 and {a.status.value for a in analyses} == {"pending"}
    assert all(a.model_version_id == active_model.id and a.roi is None for a in analyses)

    # Mientras hay análisis pendientes sigue procesando; no hay informe todavía.
    assert client.get(f"/api/cohorts/{cohort['id']}/report", headers=investigador).status_code == 409
    assert worker.process_next(db) is True
    partial = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert partial["status"] == "processing"
    assert partial["progress"] == {"total": 5, "done": 1, "failed": 0}

    assert _drain(db) == 4
    done = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert done["status"] == "done" and done["error"] is None
    assert done["progress"] == {"total": 5, "done": 5, "failed": 0}
    results = done["results"]
    assert results["patients"] == 4 and results["positive"] == 2 and results["images"] == 5
    assert 0.0 <= results["auc"] <= 1.0 and results["ci"] is not None
    assert sum(results["decisions"].values()) == 5
    assert results["abstentions"] <= 5 and results["demo"] is True
    assert results["model_hash"] == active_model.bundle_sha256
    assert len(results["csv_hash"]) == 64

    # Informe PDF y tabla.
    pdf = client.get(f"/api/cohorts/{cohort['id']}/report", headers=investigador)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    table = client.get(f"/api/cohorts/{cohort['id']}/items.csv", headers=investigador)
    rows = list(csv.reader(io.StringIO(table.text)))
    assert rows[0] == ["analysis_id", "patient_ref", "label", "probability", "decision", "status"]
    assert [(r[1], r[2], r[5]) for r in rows[1:]] == [(p, str(label), "done") for _, p, label, _ in BATCH]
    assert [int(r[0]) for r in rows[1:]] == [a.id for a in analyses]

    listing = client.get("/api/cohorts", headers=investigador).json()
    assert [c["id"] for c in listing] == [cohort["id"]] and listing[0]["status"] == "done"

    # En la bitácora solo queda el alta, sin resultados.
    logged = db.scalars(select(AuditLog).where(AuditLog.entity == "cohort")).all()
    assert [(e.action, e.entity_id, e.detail) for e in logged] == [
        ("cohort_created", cohort["id"], {})
    ]


def test_batch_images_get_the_same_deidentification_and_quality_control(
    client, db, investigador, active_model
):
    client.post(
        "/api/cohorts/batch", headers=investigador, data={"name": "uno"}, files=_files()
    )
    # Mismo lote otra vez: las imágenes se repiten, pero de otros casos (no del mismo lote).
    again = _post_batch(client, investigador, name="dos")
    assert again.status_code == 201
    flags = [i.qc_flags for i in db.scalars(select(Image).order_by(Image.id))]
    assert flags[:5] == [[]] * 5
    assert all(f == ["exact_duplicate_other_case"] for f in flags[5:])
    image = db.scalars(select(Image)).first()
    stored = get_storage().get_bytes(image.storage_key)
    assert stored.startswith(b"\x89PNG")


def test_batch_with_failed_analysis_leaves_the_cohort_failed(client, db, investigador, active_model):
    cohort = _post_batch(client, investigador).json()
    broken = db.scalars(select(Image).order_by(Image.id)).all()[2]
    get_storage().path(broken.storage_key).unlink()  # se pierde un archivo

    _drain(db)
    detail = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert detail["status"] == "failed" and detail["results"] is None
    assert detail["error"] == "1 análisis fallaron."
    assert detail["progress"] == {"total": 5, "done": 4, "failed": 1}
    assert client.get(f"/api/cohorts/{cohort['id']}/report", headers=investigador).status_code == 409
    table = client.get(f"/api/cohorts/{cohort['id']}/items.csv", headers=investigador)
    assert "failed" in table.text


def test_get_computes_the_result_if_nobody_refreshed_it(client, db, investigador, active_model):
    """Si el worker murió justo después de terminar el último análisis, el GET cierra la cohorte."""
    cohort = _post_batch(client, investigador).json()
    # Se terminan los análisis sin pasar por el worker, como si este hubiera muerto antes de refrescar.
    for analysis in db.scalars(select(Analysis)):
        analysis.status = "done"
        analysis.probability = 0.8 if analysis.id % 2 else 0.2
        analysis.decision = "indeterminate"
    db.commit()
    assert db.get(Cohort, cohort["id"]).status.value == "processing"

    detail = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert detail["status"] == "done" and detail["results"]["images"] == 5
    assert detail["results"]["decisions"] == {"indeterminate": 5}
    assert detail["results"]["abstentions"] == 5


def test_interrupted_analysis_that_runs_out_of_attempts_fails_the_cohort(
    client, db, investigador, active_model
):
    cohort = _post_batch(client, investigador).json()
    ids = list(db.scalars(select(Analysis.id).order_by(Analysis.id)))
    for analysis_id in ids[1:]:
        assert worker.process_analysis(db, analysis_id)
    stuck = db.get(Analysis, ids[0])
    stuck.status, stuck.attempts = "running", 3
    stuck.started_at = utcnow() - timedelta(minutes=10)
    db.commit()

    assert worker.requeue_stale(db) == 1
    detail = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert detail["status"] == "failed" and detail["error"] == "1 análisis fallaron."


def test_inline_worker_processes_the_batch_in_background(
    client, db, investigador, active_model, monkeypatch
):
    monkeypatch.setattr(get_settings(), "inline_worker", True)
    cohort = _post_batch(client, investigador).json()  # TestClient espera las tareas de fondo
    detail = client.get(f"/api/cohorts/{cohort['id']}", headers=investigador).json()
    assert detail["status"] == "done" and detail["results"]["images"] == 5


def test_batch_by_admin_and_ownership(client, db, investigador, admin, active_model):
    cohort = _post_batch(client, investigador).json()
    make_user(db, "otro@test.bo", Role.investigador)
    other = login(client, "otro@test.bo")
    assert client.get(f"/api/cohorts/{cohort['id']}", headers=other).status_code == 404
    assert client.get(f"/api/cohorts/{cohort['id']}", headers=admin).status_code == 200
    assert _post_batch(client, admin).status_code == 201
    assert len(client.get("/api/cohorts", headers=admin).json()) == 2
    assert len(client.get("/api/cohorts", headers=investigador).json()) == 1


# ------------------------------------------------------------------ permisos y requisitos
def test_batch_requires_research_role_and_active_model(client, db, medico, investigador):
    assert _post_batch(client, medico).status_code == 403
    no_model = _post_batch(client, investigador)
    assert no_model.status_code == 409 and "modelo activo" in no_model.json()["detail"]
    assert _counts(db) == dict.fromkeys(_counts(db), 0)


# ------------------------------------------------------------------ lote inválido: nada se escribe
def _png(seed: int) -> bytes:
    return png_bytes(noise_pixels(seed))


def _invalid_cases():
    rows = BATCH
    swapped = [(f, p, 1 - label if i == 1 else label, s) for i, (f, p, label, s) in enumerate(rows)]
    one_class = [(f, p, 1, s) for f, p, _, s in rows]
    return {
        "falta un archivo": (_files(rows)[:-1], "Faltan archivos"),
        "archivo de más": (
            [*_files(rows), ("images", ("extra.png", _png(99), "image/png"))],
            "no figuran en el manifiesto",
        ),
        "archivo repetido": (
            [*_files(rows), ("images", ("a1.png", _png(1), "image/png"))],
            "más de una vez",
        ),
        "cabecera incorrecta": (
            _files(rows, manifest=_manifest(rows, header="archivo,paciente,etiqueta")),
            "cabecera",
        ),
        "etiqueta no binaria": (
            _files(rows, manifest=_manifest(rows).replace(b",P-D,0", b",P-D,2")),
            "label debe ser 0 o 1",
        ),
        "etiquetas incoherentes por paciente": (_files(swapped), "etiqueta distinta"),
        "una sola clase": (_files(one_class), "cada clase"),
        "duplicado exacto en el lote": (
            [
                ("manifest", ("m.csv", _manifest(rows), "text/csv")),
                *[
                    ("images", (name, _png(1 if name == "d1.png" else seed), "image/png"))
                    for name, _, _, seed in rows
                ],
            ],
            "idéntica",
        ),
        "imagen que no se decodifica": (
            [
                ("manifest", ("m.csv", _manifest(rows), "text/csv")),
                *[
                    ("images", (name, b"no soy una imagen" if name == "c1.png" else _png(seed), "image/png"))
                    for name, _, _, seed in rows
                ],
            ],
            "c1.png",
        ),
        "manifiesto con columnas de más": (
            _files(rows, manifest=b"filename,patient_ref,label\na1.png,P-A,1,extra\n"),
            "tres columnas",
        ),
        "manifiesto vacío": (_files(rows, manifest=b"filename,patient_ref,label\n"), "no tiene filas"),
        "manifiesto con más de 1000 imágenes": (
            [
                (
                    "manifest",
                    ("m.csv", _manifest([(f"{i}.png", f"P-{i % 2}", i % 2, i) for i in range(1001)]), "text/csv"),
                )
            ],
            "1000",
        ),
    }


@pytest.mark.parametrize("case", list(_invalid_cases()))
def test_invalid_batch_writes_nothing(client, db, investigador, active_model, case):
    files, expected = _invalid_cases()[case]
    before_files = _stored_images()
    before = _counts(db)

    response = _post_batch(client, investigador, files=files)

    assert response.status_code == 422, response.text
    assert expected in response.json()["detail"]
    assert _counts(db) == before == dict.fromkeys(before, 0)
    assert _stored_images() == before_files
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "cohort")) == 0


def test_batch_requires_name_and_manifest(client, db, investigador, active_model):
    no_name = _post_batch(client, investigador, name=None)
    blank = _post_batch(client, investigador, name="   ")
    assert no_name.status_code == blank.status_code == 422
    assert isinstance(no_name.json()["detail"], str) and "nombre" in no_name.json()["detail"]
    no_manifest = _post_batch(client, investigador, files=_files()[1:])
    assert no_manifest.status_code == 422 and "manifiesto" in no_manifest.json()["detail"]
    assert _counts(db) == dict.fromkeys(_counts(db), 0)


def test_batch_reports_all_decode_problems_up_to_a_limit(client, db, investigador, active_model):
    rows = [(f"x{i}.png", f"P-{i % 2}", i % 2, i) for i in range(14)]
    files = [("manifest", ("m.csv", _manifest(rows), "text/csv"))]
    files += [("images", (name, b"basura", "image/png")) for name, _, _, _ in rows]
    response = _post_batch(client, investigador, files=files)
    detail = response.json()["detail"]
    assert response.status_code == 422 and "x0.png" in detail and "x9.png" in detail
    assert "x13.png" not in detail and "y 4 problemas más" in detail


def test_filenames_with_folders_match_the_manifest(client, db, investigador, active_model):
    files = [
        (key, (f"carpeta/{value[0]}", *value[1:]) if key == "images" else value)
        for key, value in _files()
    ]
    assert _post_batch(client, investigador, files=files).status_code == 201


def test_failure_while_writing_rolls_back_database_and_files(
    client, db, investigador, active_model, monkeypatch
):
    real_put = Storage.put_bytes
    writes: list[str] = []

    def flaky(self, key, data):
        if key.startswith("images/"):
            writes.append(key)
            if len(writes) == 3:
                raise OSError("disco lleno")
        real_put(self, key, data)

    monkeypatch.setattr(Storage, "put_bytes", flaky)
    before_files = _stored_images()
    with pytest.raises(OSError, match="disco lleno"):
        _post_batch(client, investigador)
    assert len(writes) == 3
    assert _counts(db) == dict.fromkeys(_counts(db), 0)
    assert _stored_images() == before_files
    assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity == "cohort")) == 0


# ------------------------------------------------------------------ límite de 1000 imágenes
def _tiny_batch(n: int) -> list:
    rows = [(f"i{i}.png", f"P-{i}", i % 2) for i in range(n)]
    manifest = "filename,patient_ref,label\n" + "".join(f"{f},{p},{label}\n" for f, p, label in rows)
    files = [("manifest", ("m.csv", manifest.encode(), "text/csv"))]
    for i, (name, _, _) in enumerate(rows):
        pixels = np.random.default_rng(i).integers(0, 255, (16, 16), dtype=np.uint8)
        files.append(("images", (name, png_bytes(pixels), "image/png")))
    return files


def test_batch_accepts_exactly_1000_images_and_rejects_1001(client, db, investigador, active_model):
    """Mil imágenes más el manifiesto son 1001 archivos: Starlette los rechazaría por defecto."""
    too_many = _post_batch(client, investigador, files=_tiny_batch(1001))
    assert too_many.status_code == 422 and "1000" in too_many.json()["detail"]
    assert _counts(db) == dict.fromkeys(_counts(db), 0)

    response = _post_batch(client, investigador, files=_tiny_batch(1000))
    assert response.status_code == 201, response.text
    assert response.json()["progress"]["total"] == 1000
    assert _counts(db)["Image"] == 1000 and _counts(db)["Case"] == 1000
