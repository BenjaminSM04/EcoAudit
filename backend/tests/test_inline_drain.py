"""Modo inline: al arrancar la API se procesan en segundo plano los análisis que quedaron pendientes."""
from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from app import worker
from app.config import get_settings
from app.main import app
from app.models import Analysis, AnalysisStatus

from .conftest import noise_pixels, png_bytes

THREAD_NAME = "ecoaudit-inline-drain"


def _queued_analysis(client, headers, seed: int = 1) -> int:
    case_id = client.post("/api/cases", headers=headers, json={"patient_ref": "P-1"}).json()["id"]
    image_id = client.post(
        f"/api/cases/{case_id}/images",
        headers=headers,
        files={"file": ("eco.png", png_bytes(noise_pixels(seed)), "image/png")},
    ).json()["id"]
    return client.post(f"/api/images/{image_id}/analyses", headers=headers, json={}).json()["id"]


def test_drain_queue_processes_every_pending_analysis(client, db, medico, active_model):
    ids = [_queued_analysis(client, medico, seed) for seed in (1, 2, 3)]

    assert worker.drain_queue() == 3
    assert worker.drain_queue() == 0  # cola vacía

    db.expire_all()
    assert {db.get(Analysis, i).status for i in ids} == {AnalysisStatus.done}


def test_inline_startup_processes_pending_analyses_in_the_background(
    client, db, medico, active_model, monkeypatch
):
    ids = [_queued_analysis(client, medico, seed) for seed in (1, 2)]
    monkeypatch.setattr(get_settings(), "inline_worker", True)

    with TestClient(app) as inline_client:
        thread = inline_client.app.state.inline_drain
        assert thread.name == THREAD_NAME and thread.daemon
        thread.join(timeout=60)
        assert not thread.is_alive()

    db.expire_all()
    assert {db.get(Analysis, i).status for i in ids} == {AnalysisStatus.done}


def test_inline_startup_does_not_block_on_the_queue(client, monkeypatch):
    release = threading.Event()

    def slow_drain() -> int:
        release.wait(timeout=30)
        return 0

    monkeypatch.setattr(worker, "drain_queue", slow_drain)
    monkeypatch.setattr(get_settings(), "inline_worker", True)

    with TestClient(app) as inline_client:
        thread = inline_client.app.state.inline_drain
        assert thread.is_alive()  # sigue trabajando y la API ya atiende
        assert inline_client.get("/api/health").status_code == 200
        release.set()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_no_inline_thread_without_inline_worker(client):
    assert get_settings().inline_worker is False  # lo fija conftest
    assert client.app.state.inline_drain is None
    assert all(t.name != THREAD_NAME for t in threading.enumerate())
