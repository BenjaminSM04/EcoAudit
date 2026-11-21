"""Indicadores, lecturas independientes, exportación FHIR y bitácora."""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Analysis, AnalysisStatus, AuditLog, Case, ClinicalReading, Image, User
from app.routers import stats


def _analysis(db, email, model_id, now, *, decision=None, shift=None, age=0, seconds=4):
    owner = db.scalar(select(User).where(User.email == email))
    case = Case(patient_ref=f"P-{decision or 'pendiente'}", created_by_id=owner.id)
    image = Image(
        storage_key="",
        pixel_sha256="0" * 64,
        dhash="0" * 16,
        width=256,
        height=256,
        source_format="png",
    )
    case.images.append(image)
    created = now - timedelta(days=age)
    analysis = Analysis(
        requested_by_id=owner.id,
        model_version_id=model_id,
        status=AnalysisStatus.done if decision else AnalysisStatus.pending,
        decision=decision,
        created_at=created,
        started_at=created + timedelta(seconds=2) if decision else None,
        finished_at=created + timedelta(seconds=seconds + 2) if decision else None,
        shift_flag=shift,
        shift_score=0.4 if shift is not None else None,
        probability=0.25 if decision else None,
        member_spread=0.1 if decision else None,
    )
    image.analyses.append(analysis)
    db.add(case)
    db.commit()
    return analysis


def test_stats_scope_calendar_and_latency(
    client, db, medico, investigador, admin, active_model, monkeypatch
):
    now = datetime(2026, 10, 31, 12, tzinfo=UTC)
    monkeypatch.setattr(stats, "utcnow", lambda: now)
    for decision, shift, age, seconds in (
        ("indeterminate", False, 0, 2),
        ("out_of_domain", True, 29, 6),
        (None, None, 30, 0),
    ):
        _analysis(
            db,
            "medico@test.bo",
            active_model.id,
            now,
            decision=decision,
            shift=shift,
            age=age,
            seconds=seconds,
        )
    _analysis(db, "investigador@test.bo", active_model.id, now, decision="probably_benign")

    url = "/api/stats/overview"
    response = client.get(url, headers=medico)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["cases"] == data["images"] == 3
    assert data["analyses_by_status"] == {"pending": 1, "running": 0, "done": 2, "failed": 0}
    assert data["decisions"]["out_of_domain"] == data["decisions"]["indeterminate"] == 1
    assert data["abstention_rate"] == data["shift_alert_rate"] == 0.5
    assert data["shift_monitored"] == 2
    assert data["active_model"] == {"name": active_model.name, "version": active_model.version}
    assert len(data["analyses_by_day"]) == 30
    assert data["analyses_by_day"][0] == {"date": "2026-10-02", "count": 1}
    assert data["analyses_by_day"][1] == {"date": "2026-10-03", "count": 0}
    assert data["analyses_by_day"][-1] == {"date": "2026-10-31", "count": 1}
    assert sum(day["count"] for day in data["analyses_by_day"]) == 2
    assert data["latency_seconds"]["processing"] == {
        "n": 2,
        "mean": 4,
        "p50": 4,
        "p95": pytest.approx(5.8),
        "max": 6,
    }
    assert data["latency_seconds"]["total"]["mean"] == 6
    assert client.get(url, headers=admin).json()["cases"] == 4

    performance = "/api/stats/performance"
    assert client.get(performance, headers=medico).status_code == 403
    scoped = client.get(performance, headers=investigador).json()["models"]
    assert scoped[0]["model_version_id"] == active_model.id
    assert scoped[0]["latency_seconds"]["processing"]["n"] == 1
    assert (
        client.get(performance, headers=admin).json()["models"][0]["latency_seconds"]["total"]["n"]
        == 3
    )


def test_readings_and_fhir(client, db, medico, investigador, admin, active_model):
    now = datetime.now(UTC)
    analysis = _analysis(db, "medico@test.bo", active_model.id, now)
    base = f"/api/analyses/{analysis.id}"
    url = f"{base}/reading"
    payload = {"birads": "4A", "blinded": True, "notes": "Lectura de prueba"}
    assert client.get(url, headers=medico).status_code == 404
    assert client.get(f"{base}/fhir", headers=medico).status_code == 409
    assert client.get(f"{base}/fhir", headers=investigador).status_code == 404
    assert client.get(url, headers=investigador).status_code == 404
    assert client.post(url, headers=investigador, json=payload).status_code == 403
    for invalid in ({"birads": "0"}, {"notes": "x" * 2001}, {"blinded": "sí"}):
        assert client.post(url, headers=medico, json=payload | invalid).status_code == 422
    created = client.post(url, headers=medico, json=payload)
    assert created.status_code == 201, created.text
    assert client.post(url, headers=medico, json=payload).status_code == 409
    assert client.post(url, headers=admin, json=payload | {"birads": "2"}).status_code == 201
    assert client.get(url, headers=medico).json() == created.json()
    assert client.get(base, headers=medico).json()["reading"] == created.json()
    assert client.get(base, headers=admin).json()["reading"]["birads"] == "2"
    case_url = f"/api/cases/{analysis.image.case_id}"
    assert (
        client.get(case_url, headers=medico).json()["images"][0]["analyses"][0]["reading"]
        == created.json()
    )
    assert client.get("/api/stats/overview", headers=admin).json()["clinical_readings"] == 2
    assert client.get("/api/stats/overview", headers=medico).json()["clinical_readings"] == 1

    analysis.status = AnalysisStatus.done
    analysis.finished_at = now
    analysis.probability = 0.8
    analysis.member_spread = 0.05
    analysis.decision = "suspicious"
    analysis.shift_flag = False
    db.commit()
    result = client.get(f"{base}/fhir", headers=medico)
    assert result.status_code == 200 and result.headers["content-type"] == "application/fhir+json"
    assert "Lectura de prueba" not in result.text
    bundle = result.json()
    assert bundle["resourceType"] == "Bundle" and bundle["type"] == "collection"
    entries = {r["fullUrl"]: r["resource"] for r in bundle["entry"]}
    assert all(url.startswith("urn:uuid:") for url in entries)
    assert len(entries) == 5
    report = next(r for r in entries.values() if r["resourceType"] == "DiagnosticReport")
    assert report["status"] == "final" and "Prototipo de investigación" in report["conclusion"]
    assert report["effectiveDateTime"] == now.isoformat()
    assert entries[report["subject"]["reference"]] == {
        "resourceType": "Patient",
        "identifier": [{"value": "P-pendiente"}],
    }
    model_result, clinical = [entries[ref["reference"]] for ref in report["result"]]
    assert model_result["subject"] == clinical["subject"] == report["subject"]
    assert model_result["valueQuantity"]["value"] == 0.8
    assert model_result["component"][0]["valueQuantity"]["value"] == 0.05
    assert "dataAbsentReason" in model_result["component"][1]
    assert model_result["component"][2]["valueBoolean"] is False
    assert clinical["valueCodeableConcept"]["text"] == "4A"
    device = entries[model_result["device"]["reference"]]
    assert device["deviceName"][0]["name"] == active_model.name
    assert device["version"][0]["value"] == active_model.version
    assert device["identifier"][0]["value"] == active_model.bundle_sha256
    assert len(client.get(f"{base}/fhir", headers=admin).json()["entry"]) == 6
    actions = db.scalars(select(AuditLog.action).where(AuditLog.entity == "analysis")).all()
    assert actions.count("clinical_reading_created") == actions.count("analysis_fhir_exported") == 2


def test_concordance_matrix_and_undefined_kappa(client, db, medico, investigador, active_model):
    now = datetime.now(UTC)
    reader = db.scalar(select(User).where(User.email == "medico@test.bo"))
    for decision, category, blinded in (
        ("probably_benign", "1", True),
        ("probably_benign", "2", True),
        ("suspicious", "3", False),
        ("suspicious", "4A", True),
        ("indeterminate", "6", False),
        ("out_of_domain", "5", True),
        (None, "4B", True),
    ):
        analysis = _analysis(db, reader.email, active_model.id, now, decision=decision)
        db.add(
            ClinicalReading(
                analysis_id=analysis.id, reader_id=reader.id, birads=category, blinded=blinded
            )
        )
    db.commit()
    url = "/api/stats/concordance"
    result = client.get(url, headers=medico).json()
    assert result["matrix"] == [[2, 1], [0, 1]]
    assert result["agreement_percent"] == 75
    assert result["kappa"] == pytest.approx(0.5)
    assert result["n"] == 5 and result["n_indeterminate"] == 1
    assert (result["n_blinded"], result["n_unblinded"]) == (3, 2)
    assert result["birads"]["6"] == 1 and result["birads"]["5"] == 0
    empty = client.get(url, headers=investigador).json()
    assert empty["n"] == 0 and empty["kappa"] is empty["agreement_percent"] is None


def test_audit_filters_order_and_csv(client, db, medico, admin):
    user = db.scalar(select(User).where(User.email == "medico@test.bo"))
    now = datetime.now(UTC)
    for age in (4, 1, 1):
        db.add(
            AuditLog(
                user_id=user.id,
                action="prueba",
                entity="case",
                detail={"origen": "ecografía"},
                created_at=now - timedelta(days=age),
            )
        )
    db.commit()
    url = "/api/audit-log"
    filters = {
        "user_id": user.id,
        "action": "prueba",
        "desde": (now - timedelta(days=1)).isoformat(),
        "hasta": now.isoformat(),
        "limit": 1,
    }
    assert client.get(url, headers=medico).status_code == 403
    assert client.get(f"{url}.csv", headers=medico).status_code == 403
    first = client.get(url, headers=admin, params=filters).json()
    second = client.get(url, headers=admin, params=filters | {"offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] > second["items"][0]["id"]
    response = client.get(f"{url}.csv", headers=admin, params=filters | {"offset": 1})
    assert response.status_code == 200 and response.headers["X-Total-Count"] == "2"
    assert response.headers["content-type"].startswith("text/csv")
    (row,) = csv.DictReader(io.StringIO(response.text))
    assert row["id"] == str(second["items"][0]["id"])
    assert row["detail"] == '{"origen": "ecografía"}'
    assert client.get(url, headers=admin, params={"limit": 501}).status_code == 422
    assert (
        client.get(url, headers=admin, params={"desde": "2026-01-01T00:00:00"}).status_code == 422
    )
