from __future__ import annotations

from sqlalchemy import select

from app import worker
from app.models import AuditLog, Role

from .conftest import PASSWORD, login, make_user, noise_pixels, png_bytes


def _upload(client, headers, case_id: int, seed: int = 0):
    return client.post(
        f"/api/cases/{case_id}/images",
        headers=headers,
        files={"file": ("eco.png", png_bytes(noise_pixels(seed)), "image/png")},
    )


def _new_case(client, headers) -> int:
    response = client.post("/api/cases", headers=headers, json={"patient_ref": "P-001"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ------------------------------------------------------------------ autenticación y roles
def test_login_rejects_wrong_password_and_inactive_users(client, db):
    user = make_user(db, "a@test.bo", Role.medico)
    bad = client.post("/api/auth/login", data={"username": "a@test.bo", "password": "x" * 12})
    assert bad.status_code == 401

    user.is_active = False
    db.commit()
    blocked = client.post("/api/auth/login", data={"username": "a@test.bo", "password": PASSWORD})
    assert blocked.status_code == 401


def test_endpoints_require_authentication(client):
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_only_admin_manages_users_and_models(client, medico, admin, active_model):
    assert client.get("/api/users", headers=medico).status_code == 403
    assert client.post(f"/api/models/{active_model.id}/activate", headers=medico).status_code == 403

    created = client.post(
        "/api/users",
        headers=admin,
        json={
            "email": "Nuevo@Test.bo",
            "full_name": "Nuevo",
            "password": "x" * 12,
            "role": "medico",
        },
    )
    assert created.status_code == 201 and created.json()["email"] == "nuevo@test.bo"
    duplicate = client.post(
        "/api/users",
        headers=admin,
        json={"email": "nuevo@test.bo", "full_name": "N", "password": "x" * 12, "role": "medico"},
    )
    assert duplicate.status_code == 409


def test_admin_cannot_lock_themselves_out(client, admin):
    me = client.get("/api/auth/me", headers=admin).json()
    response = client.patch(f"/api/users/{me['id']}", headers=admin, json={"is_active": False})
    assert response.status_code == 400


def test_investigador_uses_cases_but_only_his_own(client, db, medico, admin):
    make_user(db, "inv@test.bo", Role.investigador)
    inv = login(client, "inv@test.bo")
    make_user(db, "inv2@test.bo", Role.investigador)
    other = login(client, "inv2@test.bo")

    case_id = _new_case(client, inv)
    image_id = _upload(client, inv, case_id).json()["id"]
    assert [c["id"] for c in client.get("/api/cases", headers=inv).json()] == [case_id]
    assert client.get(f"/api/cases/{case_id}", headers=inv).status_code == 200

    # Los casos de otros (médico, otro investigador) no se ven; los propios, sí; admin ve todo.
    medico_case = _new_case(client, medico)
    for headers in (medico, other):
        assert client.get(f"/api/cases/{case_id}", headers=headers).status_code == 404
    assert client.get(f"/api/cases/{medico_case}", headers=inv).status_code == 404
    assert client.get(f"/api/images/{image_id}/file", headers=other).status_code == 404
    assert client.get("/api/analyses/1", headers=other).status_code == 404
    assert _upload(client, other, case_id).status_code == 404
    assert (
        client.post(f"/api/images/{image_id}/analyses", headers=other, json={}).status_code == 404
    )
    assert client.get(f"/api/cases/{case_id}", headers=admin).status_code == 200


# ------------------------------------------------------------------ aislamiento entre médicos
def test_medico_cannot_see_cases_of_another_medico(client, db, medico, admin):
    case_id = _new_case(client, medico)
    image_id = _upload(client, medico, case_id).json()["id"]

    make_user(db, "otro@test.bo", Role.medico)
    other = login(client, "otro@test.bo")

    assert client.get("/api/cases", headers=other).json() == []
    assert client.get(f"/api/cases/{case_id}", headers=other).status_code == 404
    assert client.get(f"/api/images/{image_id}/file", headers=other).status_code == 404
    assert _upload(client, other, case_id).status_code == 404
    # El administrador sí los ve.
    assert client.get(f"/api/cases/{case_id}", headers=admin).status_code == 200


# ------------------------------------------------------------------ carga de imágenes
def test_upload_flags_duplicates_within_a_case(client, medico):
    case_id = _new_case(client, medico)
    first = _upload(client, medico, case_id, seed=1).json()
    second = _upload(client, medico, case_id, seed=1).json()
    third = _upload(client, medico, case_id, seed=2).json()

    assert first["qc_flags"] == [] and first["duplicate_of_id"] is None
    assert "exact_duplicate" in second["qc_flags"] and second["duplicate_of_id"] == first["id"]
    assert third["duplicate_of_id"] is None

    stored = client.get(f"/api/images/{first['id']}/file", headers=medico)
    assert stored.status_code == 200 and stored.headers["content-type"] == "image/png"


def test_upload_rejects_non_images(client, medico):
    case_id = _new_case(client, medico)
    response = client.post(
        f"/api/cases/{case_id}/images",
        headers=medico,
        files={"file": ("virus.exe", b"MZ\x90\x00 no soy una imagen", "application/octet-stream")},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------ análisis de punta a punta
def test_analysis_requires_an_active_model(client, medico):
    case_id = _new_case(client, medico)
    image_id = _upload(client, medico, case_id).json()["id"]
    response = client.post(f"/api/images/{image_id}/analyses", headers=medico, json={})
    assert response.status_code == 409


def test_analysis_end_to_end(client, db, medico, active_model):
    case_id = _new_case(client, medico)
    image_id = _upload(client, medico, case_id).json()["id"]

    queued = client.post(
        f"/api/images/{image_id}/analyses",
        headers=medico,
        json={"roi": {"x": 40, "y": 40, "w": 120, "h": 100}},
    )
    assert queued.status_code == 202
    analysis = queued.json()
    assert analysis["status"] == "pending" and analysis["probability"] is None
    assert client.get(f"/api/analyses/{analysis['id']}/cam", headers=medico).status_code == 404

    assert worker.process_next(db) is True
    assert worker.process_next(db) is False  # la cola quedó vacía

    done = client.get(f"/api/analyses/{analysis['id']}", headers=medico).json()
    assert done["status"] == "done", done["error"]
    assert 0.0 < done["probability"] < 1.0
    assert done["decision"] in {"probably_benign", "indeterminate", "suspicious", "out_of_domain"}
    assert done["model_version_id"] == active_model.id
    assert "demo_model" in done["warnings"]
    cam = client.get(f"/api/analyses/{analysis['id']}/cam", headers=medico)
    assert cam.status_code == 200 and cam.content[:8] == b"\x89PNG\r\n\x1a\n"

    case = client.get(f"/api/cases/{case_id}", headers=medico).json()
    assert case["images"][0]["analyses"][0]["id"] == analysis["id"]

    actions = set(db.scalars(select(AuditLog.action)))
    assert {"login", "case_created", "image_uploaded", "analysis_requested"} <= actions


def test_analysis_rejects_roi_outside_image(client, medico, active_model):
    case_id = _new_case(client, medico)
    image_id = _upload(client, medico, case_id).json()["id"]
    response = client.post(
        f"/api/images/{image_id}/analyses",
        headers=medico,
        json={"roi": {"x": 200, "y": 200, "w": 200, "h": 200}},
    )
    assert response.status_code == 422


def test_a_claimed_analysis_is_not_processed_twice(client, db, medico, active_model):
    case_id = _new_case(client, medico)
    image_id = _upload(client, medico, case_id).json()["id"]
    analysis_id = client.post(f"/api/images/{image_id}/analyses", headers=medico, json={}).json()[
        "id"
    ]

    assert worker.claim(db, analysis_id) is True
    assert worker.claim(db, analysis_id) is False
    assert worker.process_analysis(db, analysis_id) is False


def test_failed_analysis_reports_error_instead_of_crashing(client, db, medico, active_model):
    case_id = _new_case(client, medico)
    image = _upload(client, medico, case_id).json()
    analysis_id = client.post(
        f"/api/images/{image['id']}/analyses", headers=medico, json={}
    ).json()["id"]

    from app.models import Image
    from app.storage import get_storage

    get_storage().path(db.get(Image, image["id"]).storage_key).unlink()  # se pierde el archivo

    assert worker.process_next(db) is True
    failed = client.get(f"/api/analyses/{analysis_id}", headers=medico).json()
    assert failed["status"] == "failed" and "FileNotFoundError" in failed["error"]
    assert failed["probability"] is None
