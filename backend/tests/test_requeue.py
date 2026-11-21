"""Análisis interrumpidos: el worker murió con el análisis en ``running``."""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from app import worker
from app.config import get_settings
from app.main import app
from app.models import Analysis, AnalysisStatus, utcnow

from .conftest import noise_pixels, png_bytes


def _queued_analysis(client, headers) -> int:
    case_id = client.post("/api/cases", headers=headers, json={"patient_ref": "P-1"}).json()["id"]
    image_id = client.post(
        f"/api/cases/{case_id}/images",
        headers=headers,
        files={"file": ("eco.png", png_bytes(noise_pixels(1)), "image/png")},
    ).json()["id"]
    return client.post(f"/api/images/{image_id}/analyses", headers=headers, json={}).json()["id"]


def _make_stale(db, analysis_id: int, minutes: int = 10) -> None:
    """Deja el análisis ``running`` desde hace ``minutes`` minutos, como si el worker hubiera muerto."""
    analysis = db.get(Analysis, analysis_id)
    analysis.status = AnalysisStatus.running
    analysis.started_at = utcnow() - timedelta(minutes=minutes)
    db.commit()


def test_claim_counts_attempts(client, db, medico, active_model):
    analysis_id = _queued_analysis(client, medico)
    assert client.get(f"/api/analyses/{analysis_id}", headers=medico).json()["attempts"] == 0
    assert worker.claim(db, analysis_id) is True
    db.expire_all()
    assert db.get(Analysis, analysis_id).attempts == 1
    assert client.get(f"/api/analyses/{analysis_id}", headers=medico).json()["attempts"] == 1


def test_stale_running_analysis_goes_back_to_the_queue_and_is_processed(
    client, db, medico, active_model
):
    analysis_id = _queued_analysis(client, medico)
    assert worker.claim(db, analysis_id)
    _make_stale(db, analysis_id)

    assert worker.requeue_stale(db) == 1
    db.expire_all()
    analysis = db.get(Analysis, analysis_id)
    assert analysis.status == AnalysisStatus.pending and analysis.attempts == 1
    assert analysis.started_at is None and analysis.error is None

    assert worker.process_next(db) is True
    done = client.get(f"/api/analyses/{analysis_id}", headers=medico).json()
    assert done["status"] == "done" and done["attempts"] == 2


def test_recent_running_analysis_is_left_alone(client, db, medico, active_model):
    analysis_id = _queued_analysis(client, medico)
    assert worker.claim(db, analysis_id)
    assert worker.requeue_stale(db) == 0
    db.expire_all()
    assert db.get(Analysis, analysis_id).status == AnalysisStatus.running


def test_timeout_comes_from_settings(client, db, medico, active_model, monkeypatch):
    analysis_id = _queued_analysis(client, medico)
    assert worker.claim(db, analysis_id)
    _make_stale(db, analysis_id, minutes=1)  # 60 s: dentro del plazo por defecto (300 s)
    assert worker.requeue_stale(db) == 0
    monkeypatch.setattr(get_settings(), "analysis_timeout_seconds", 30)
    assert worker.requeue_stale(db) == 1


def test_analysis_interrupted_three_times_ends_as_failed(client, db, medico, active_model):
    analysis_id = _queued_analysis(client, medico)
    for attempt in (1, 2):
        assert worker.claim(db, analysis_id)
        _make_stale(db, analysis_id)
        assert worker.requeue_stale(db) == 1
        db.expire_all()
        assert db.get(Analysis, analysis_id).status == AnalysisStatus.pending
        assert db.get(Analysis, analysis_id).attempts == attempt

    assert worker.claim(db, analysis_id)  # tercer intento
    _make_stale(db, analysis_id)
    assert worker.requeue_stale(db) == 1

    failed = client.get(f"/api/analyses/{analysis_id}", headers=medico).json()
    assert failed["status"] == "failed" and failed["attempts"] == 3
    assert failed["error"] == "Interrumpido repetidamente."
    assert failed["finished_at"] is not None
    assert worker.process_next(db) is False  # ya no vuelve a la cola


def test_requeue_does_not_touch_other_states(client, db, medico, active_model):
    pending = _queued_analysis(client, medico)
    finished = _queued_analysis(client, medico)
    assert worker.process_analysis(db, finished)
    assert worker.requeue_stale(db) == 0
    db.expire_all()
    assert db.get(Analysis, pending).status == AnalysisStatus.pending
    assert db.get(Analysis, finished).status == AnalysisStatus.done


def test_api_startup_requeues_stale_analyses(client, db, medico, active_model):
    analysis_id = _queued_analysis(client, medico)
    assert worker.claim(db, analysis_id)
    _make_stale(db, analysis_id)

    with TestClient(app):  # al arrancar la API
        pass

    db.expire_all()
    assert db.get(Analysis, analysis_id).status == AnalysisStatus.pending
