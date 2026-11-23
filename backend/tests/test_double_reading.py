from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Analysis, AnalysisStatus, Case, Image, ModelVersion, Role, User
from app.routers import cases, stats
from app.storage import get_storage

from .conftest import login, make_user


def _case(db, email, ref):
    owner = db.scalar(select(User).where(User.email == email))
    case = Case(created_by_id=owner.id, patient_ref=ref)
    db.add(case)
    db.flush()
    image = Image(
        case_id=case.id,
        storage_key=f"test/{case.id}.png",
        pixel_sha256="a" * 64,
        dhash="0" * 16,
        width=256,
        height=256,
        source_format="PNG",
    )
    db.add(image)
    db.flush()
    get_storage().put_bytes(image.storage_key, b"prueba")
    return case, image


def _analysis(db, case, image, model, when, **overrides):
    fields = dict(
        image_id=image.id,
        requested_by_id=case.created_by_id,
        model_version_id=model.id,
        status=AnalysisStatus.done,
        probability=0.75,
        decision="suspicious",
        created_at=when - timedelta(seconds=3),
        finished_at=when,
    )
    analysis = Analysis(**(fields | overrides))
    db.add(analysis)
    db.flush()
    return analysis


def _read(client, analysis, headers, birads):
    response = client.post(
        f"/api/analyses/{analysis.id}/reading",
        headers=headers,
        json={"birads": birads, "blinded": True},
    )
    assert response.status_code == 201, response.text


def test_assignment_isolation_worklist_and_pdf(
    client, db, medico, admin, investigador, active_model, monkeypatch
):
    second = make_user(db, "segundo@test.bo", Role.medico)
    second_headers = login(client, second.email)
    unrelated = make_user(db, "ajeno@test.bo", Role.medico)
    other = login(client, unrelated.email)
    case, image = _case(db, "medico@test.bo", "PAC-1000")
    own_case, own_image = _case(db, second.email, "PAC-1001")
    private_case, private_image = _case(db, unrelated.email, "PAC-1002")
    now = datetime.now(UTC)
    result = {
        "probability_raw": 0.8,
        "probability": 0.75,
        "member_spread": 0.15,
        "decision": "suspicious",
        "shift_score": 0.9,
        "shift_flag": True,
        "warnings": ["out_of_domain"],
        "has_cam": True,
    }
    cam_key = "test/mapa.png"
    get_storage().put_bytes(cam_key, b"mapa de prueba")
    oldest = _analysis(
        db,
        case,
        image,
        active_model,
        now - timedelta(days=2),
        cam_key=cam_key,
        **{key: value for key, value in result.items() if key != "has_cam"},
    )
    newer = _analysis(db, case, image, active_model, now)
    own = _analysis(db, own_case, own_image, active_model, now - timedelta(days=1))
    _analysis(db, private_case, private_image, active_model, now)
    _analysis(db, case, image, active_model, now, status=AnalysisStatus.pending, finished_at=None)
    db.commit()

    url = f"/api/cases/{case.id}"
    analysis_url = f"/api/analyses/{oldest.id}"
    image_url = f"/api/images/{image.id}"
    for path in (
        url,
        f"{url}/readers",
        f"{image_url}/file",
        analysis_url,
        f"{analysis_url}/reading",
        f"{analysis_url}/cam",
        f"{analysis_url}/fhir",
        f"{analysis_url}/report",
    ):
        for headers in (second_headers, other, investigador):
            assert client.get(path, headers=headers).status_code == 404
    for headers in (other, investigador):
        assert (
            client.post(
                f"{url}/readers", headers=headers, json={"reader_id": second.id}
            ).status_code
            == 404
        )
    assert (
        client.post(
            f"{url}/readers", headers=medico, json={"reader_id": case.created_by_id}
        ).status_code
        == 422
    )
    assigned = client.post(f"{url}/readers", headers=medico, json={"reader_id": second.id})
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["assigned_by"] == case.created_by_id
    assert (
        client.post(f"{url}/readers", headers=admin, json={"reader_id": second.id}).status_code
        == 409
    )
    assert client.get(f"{url}/readers", headers=admin).json()["assigned"] == [
        {"id": second.id, "full_name": second.full_name}
    ]
    assert {row["id"] for row in client.get("/api/cases", headers=second_headers).json()} == {
        case.id,
        own_case.id,
    }
    assert client.get(url, headers=second_headers).json()["can_manage"] is False
    assert client.get(f"{image_url}/file", headers=second_headers).status_code == 200

    def assert_blinded():
        direct = client.get(analysis_url, headers=second_headers)
        detail = client.get(url, headers=second_headers)
        assert direct.status_code == detail.status_code == 200
        assert direct.headers["Cache-Control"] == detail.headers["Cache-Control"] == "no-store"
        for item in (direct.json(), detail.json()["images"][0]["analyses"][0]):
            assert item["blinded_for_reader"] is True
            assert item["reading"] is None
            assert item["warnings"] == []
            assert item["has_cam"] is False
            assert "cam_key" not in item
            assert all(
                item[field] is None for field in result if field not in ("warnings", "has_cam")
            )
        for suffix in ("cam", "report", "fhir"):
            response = client.get(f"{analysis_url}/{suffix}", headers=second_headers)
            assert response.status_code == 403
            assert response.json()["detail"].startswith("Registre su lectura")
        overview = client.get("/api/stats/overview", headers=second_headers).json()
        assert overview["decisions"]["suspicious"] == 1  # Solo el análisis propio.
        assert overview["shift_alert_rate"] == 0
        assert overview["shift_monitored"] == 0
        assert client.get("/api/stats/concordance", headers=second_headers).json()["n"] == 0

    assert_blinded()
    for manager in (medico, admin):
        item = client.get(analysis_url, headers=manager).json()
        assert item["blinded_for_reader"] is False
        assert {key: item[key] for key in result} == result
        for suffix in ("cam", "report", "fhir"):
            assert client.get(f"{analysis_url}/{suffix}", headers=manager).status_code == 200
    for path, payload in (
        (f"{url}/images", {"files": {"file": ("eco.png", b"x")}}),
        (f"{image_url}/roi", {}),
        (f"{image_url}/analyses", {"json": {"roi": None}}),
        (f"{url}/readers", {"json": {"reader_id": unrelated.id}}),
    ):
        assert client.post(path, headers=second_headers, **payload).status_code == 403
        assert client.post(path, headers=other, **payload).status_code == 404
    assert (
        client.post(
            f"{analysis_url}/reading", headers=other, json={"birads": "2", "blinded": True}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{analysis_url}/reading",
            headers=investigador,
            json={"birads": "2", "blinded": True},
        ).status_code
        == 404
    )
    assert client.get("/api/worklist", headers=admin).status_code == 403
    assert client.get("/api/worklist", headers=investigador).status_code == 403

    def pending():
        response = client.get("/api/worklist", headers=second_headers)
        assert response.status_code == 200, response.text
        assert all(row.keys().isdisjoint(result) for row in response.json())
        return [row["analysis_id"] for row in response.json()]

    assert pending() == [oldest.id, own.id, newer.id]
    _read(client, oldest, medico, "2")
    assert pending() == [oldest.id, own.id, newer.id]
    assert_blinded()
    saved = client.post(
        f"{analysis_url}/reading", headers=second_headers, json={"birads": "4A", "blinded": False}
    )
    assert saved.status_code == 201
    assert saved.json()["blinded"] is True
    assert pending() == [own.id, newer.id]
    assert client.get(f"{analysis_url}/reading", headers=second_headers).json() == saved.json()
    direct = client.get(analysis_url, headers=second_headers).json()
    nested = client.get(url, headers=second_headers).json()["images"][0]["analyses"]
    assert direct == nested[0]
    assert nested[1]["blinded_for_reader"] is True
    assert direct["blinded_for_reader"] is False
    assert {key: direct[key] for key in result} == result
    cam = client.get(f"{analysis_url}/cam", headers=second_headers)
    assert cam.content == b"mapa de prueba" and cam.headers["Cache-Control"] == "no-store"
    assert client.get(f"{analysis_url}/fhir", headers=second_headers).status_code == 200
    overview = client.get("/api/stats/overview", headers=second_headers).json()
    assert overview["decisions"]["suspicious"] == 2
    assert overview["shift_alert_rate"] == 0.5
    assert overview["shift_monitored"] == 1
    assert client.get(f"{analysis_url}/report", headers=second_headers).content.startswith(b"%PDF")

    monkeypatch.setattr(cases, "pdf", lambda title, fields: dict(fields))
    own_pdf = client.get(f"{analysis_url}/report", headers=second_headers).json()
    assert "BI-RADS 4A · Ciega ·" in own_pdf["Lectura clínica"]
    assert "UTC" in own_pdf["Lectura clínica"]
    assert own_pdf["Concordancia con el modelo"].startswith("Coincide")
    assert (
        client.get(f"{analysis_url}/report", headers=medico)
        .json()["Concordancia con el modelo"]
        .startswith("Discrepa")
    )
    assert "Lectura clínica" not in client.get(f"{analysis_url}/report", headers=admin).json()


def test_inter_reader_pairs_and_researcher_scope(
    client, db, admin, medico, investigador, active_model
):
    second = make_user(db, "segundo@test.bo", Role.medico)
    third = make_user(db, "tercero@test.bo", Role.medico)
    second_headers = login(client, second.email)
    third_headers = login(client, third.email)
    case, image = _case(db, "investigador@test.bo", "PAC-1000")
    outside_case, outside_image = _case(db, "medico@test.bo", "PAC-1001")
    first = db.scalar(select(User).where(User.email == "medico@test.bo"))
    db.commit()
    readers_url = f"/api/cases/{case.id}/readers"
    for reader in (first, second, third):
        assert (
            client.post(readers_url, headers=admin, json={"reader_id": reader.id}).status_code
            == 201
        )
    assert (
        client.post(
            f"/api/cases/{outside_case.id}/readers", headers=admin, json={"reader_id": second.id}
        ).status_code
        == 201
    )
    now = datetime.now(UTC)
    analyses = [_analysis(db, case, image, active_model, now) for _ in range(5)]
    outside = _analysis(db, outside_case, outside_image, active_model, now)
    db.commit()
    for analysis, (a, b) in zip(
        analyses, (("2", "2"), ("3", "4A"), ("4A", "4B"), ("5", "5")), strict=False
    ):
        _read(client, analysis, medico, a)
        _read(client, analysis, second_headers, b)
    _read(client, analyses[0], third_headers, "2")
    _read(client, analyses[4], medico, "1")
    _read(client, analyses[4], admin, "6")
    _read(client, outside, medico, "3")
    _read(client, outside, second_headers, "3")

    url = "/api/stats/inter-reader"
    assert client.get(url, headers=medico).status_code == 403
    scoped = client.get(url, headers=investigador).json()
    assert scoped["n"] == 4 and len(scoped["pairs"]) == 3
    pair = scoped["pairs"][0]
    assert pair["readers"] == [
        {"id": user.id, "full_name": user.full_name} for user in (first, second)
    ]
    assert pair["n"] == 4 and pair["agreement_percent"] == 50
    assert pair["kappa"] == pytest.approx(0.5)
    assert pair["weighted_kappa"] == pytest.approx(1 - 8 / 34)
    assert scoped["pairs"][1]["kappa"] is None and scoped["pairs"][1]["weighted_kappa"] is None
    total = client.get(url, headers=admin).json()
    assert total["n"] == 5 and total["pairs"][0]["n"] == 5


def test_drift_week_boundaries_alert_and_scope(
    client, db, admin, medico, investigador, active_model, monkeypatch
):
    now = datetime(2026, 1, 1, 12, tzinfo=UTC)
    monkeypatch.setattr(stats, "utcnow", lambda: now)
    case, image = _case(db, "investigador@test.bo", "PAC-1000")
    outside, outside_image = _case(db, "medico@test.bo", "PAC-1001")
    other_model = ModelVersion(
        name="Otro", version="1", bundle_sha256="b" * 64, card={}, storage_key="otro"
    )
    db.add(other_model)
    db.flush()
    monday = now - timedelta(days=3, hours=12)
    for index in range(10):
        _analysis(
            db,
            case,
            image,
            active_model,
            monday,
            shift_flag=index < 4,
            shift_score=0.25 if index < 4 else None,
            decision=(
                "out_of_domain" if index < 4 else "indeterminate" if index == 4 else "suspicious"
            ),
        )
    _analysis(db, case, image, active_model, monday - timedelta(seconds=1), shift_flag=True)
    _analysis(db, case, image, active_model, monday - timedelta(weeks=12))
    _analysis(db, case, image, active_model, now, status=AnalysisStatus.failed)
    for _ in range(9):
        _analysis(db, case, image, other_model, now, shift_flag=True)
    _analysis(db, outside, outside_image, active_model, now, shift_flag=False)
    db.commit()
    url = "/api/stats/drift"
    assert client.get(url, headers=medico).status_code == 403
    scoped = client.get(url, headers=investigador).json()
    assert len(scoped["weeks"]) == 12 and scoped["weeks"][-1] == "2025-12-29"
    assert scoped["alert_threshold"] == 0.3
    weeks = scoped["models"][0]["weeks"]
    assert weeks[-1] == {
        "week": "2025-12-29",
        "n": 10,
        "shift_alert_rate": 0.4,
        "mean_shift_score": 0.25,
        "abstention_rate": 0.5,
        "alert": True,
    }
    assert weeks[-2]["n"] == 1 and not weeks[-2]["alert"]
    assert weeks[0]["n"] == 0 and weeks[0]["shift_alert_rate"] is None
    assert not scoped["models"][1]["weeks"][-1]["alert"]
    assert client.get(url, headers=admin).json()["models"][0]["weeks"][-1]["n"] == 11
    monkeypatch.setattr(stats.get_settings(), "drift_alert_rate", 0.4)
    assert not client.get(url, headers=investigador).json()["models"][0]["weeks"][-1]["alert"]
