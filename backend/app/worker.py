"""Worker de inferencia.

La cola es la propia tabla ``analyses`` (estado ``pending``). Un análisis se reclama con un
UPDATE condicionado, que es atómico en PostgreSQL y SQLite, así que varios workers pueden
convivir sin procesar dos veces el mismo trabajo (ver ``docs/adr/0002-cola-en-base-de-datos.md``).

Uso: ``python -m app.worker``
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .cohorts import refresh_cohorts_of
from .config import get_settings
from .db import init_db, new_session
from .models import Analysis, AnalysisStatus, utcnow
from .pipeline.bundle import ModelBundle
from .pipeline.imaging import load_png
from .pipeline.runner import analyze
from .storage import get_storage

log = logging.getLogger("ecoaudit.worker")

# Veces que se reclama un análisis antes de darlo por fallido si el worker muere en cada intento.
MAX_ATTEMPTS = 3
INTERRUPTED_ERROR = "Interrumpido repetidamente."

_bundles: dict[int, ModelBundle] = {}


def _get_bundle(model_version_id: int, storage_key: str) -> ModelBundle:
    if model_version_id not in _bundles:
        _bundles[model_version_id] = ModelBundle(get_storage().path(storage_key))
    return _bundles[model_version_id]


def claim(db: Session, analysis_id: int) -> bool:
    """Pasa el análisis de pending a running. False si otro proceso ya lo tomó."""
    result = db.execute(
        update(Analysis)
        .where(Analysis.id == analysis_id, Analysis.status == AnalysisStatus.pending)
        .values(
            status=AnalysisStatus.running, started_at=utcnow(), attempts=Analysis.attempts + 1
        )
    )
    db.commit()
    return result.rowcount == 1


def requeue_stale(db: Session) -> int:
    """Recupera los análisis que quedaron ``running`` porque el worker murió.

    Los que llevan más de ``analysis_timeout_seconds`` en ese estado vuelven a ``pending`` si les
    quedan intentos; si no, pasan a ``failed``. Cada cambio es un UPDATE condicionado al estado
    ``running``, así que no pisa a un worker que justo terminó. Devuelve cuántos cambió.
    """
    cutoff = utcnow() - timedelta(seconds=get_settings().analysis_timeout_seconds)
    stale = (Analysis.status == AnalysisStatus.running, Analysis.started_at < cutoff)
    # Los que agotaron los intentos fallan; se guardan sus ids para cerrar sus cohortes.
    exhausted = list(
        db.scalars(select(Analysis.id).where(*stale, Analysis.attempts >= MAX_ATTEMPTS))
    )
    failed = 0
    if exhausted:
        failed = db.execute(
            update(Analysis)
            .where(Analysis.id.in_(exhausted), *stale)
            .values(
                status=AnalysisStatus.failed, error=INTERRUPTED_ERROR, finished_at=utcnow()
            )
        ).rowcount
    requeued = db.execute(
        update(Analysis)
        .where(*stale, Analysis.attempts < MAX_ATTEMPTS)
        .values(status=AnalysisStatus.pending, started_at=None)
    ).rowcount
    db.commit()
    if requeued or failed:
        log.warning("Análisis interrumpidos: %d reencolados, %d fallidos", requeued, failed)
    for analysis_id in exhausted:
        _refresh_cohorts(db, analysis_id)
    return requeued + failed


def _refresh_cohorts(db: Session, analysis_id: int) -> None:
    """Cierra las cohortes del análisis; un error aquí no debe tumbar al worker."""
    try:
        refresh_cohorts_of(db, analysis_id)
    except Exception:
        log.exception("No se pudo refrescar la cohorte del análisis %s", analysis_id)
        db.rollback()


def process_analysis(db: Session, analysis_id: int) -> bool:
    """Ejecuta un análisis pendiente. Devuelve False si no estaba disponible."""
    if not claim(db, analysis_id):
        return False
    db.expire_all()
    analysis = db.get(Analysis, analysis_id)
    storage = get_storage()
    try:
        bundle = _get_bundle(analysis.model_version_id, analysis.model_version.storage_key)
        rgb = load_png(storage.get_bytes(analysis.image.storage_key))
        result = analyze(rgb, analysis.roi, bundle)
        cam_key = f"cams/{analysis.id}.png"
        storage.put_bytes(cam_key, result.cam_overlay_png)

        analysis.probability_raw = result.probability_raw
        analysis.probability = result.probability
        analysis.member_spread = result.member_spread
        analysis.decision = result.decision
        analysis.shift_score = result.shift_score
        analysis.shift_flag = result.shift_flag
        analysis.warnings = [*result.warnings, *analysis.image.qc_flags]
        analysis.cam_key = cam_key
        analysis.status = AnalysisStatus.done
    except Exception as exc:  # el worker no debe morir por un análisis fallido
        log.exception("Análisis %s falló", analysis_id)
        db.rollback()
        analysis = db.get(Analysis, analysis_id)
        analysis.status = AnalysisStatus.failed
        analysis.error = f"{type(exc).__name__}: {exc}"[:2000]
    analysis.finished_at = utcnow()
    db.commit()
    _refresh_cohorts(db, analysis_id)
    return True


def process_next(db: Session) -> bool:
    """Procesa el análisis pendiente más antiguo. False si la cola está vacía."""
    while True:
        analysis_id = db.scalar(
            select(Analysis.id)
            .where(Analysis.status == AnalysisStatus.pending)
            .order_by(Analysis.id)
            .limit(1)
        )
        if analysis_id is None:
            return False
        if process_analysis(db, analysis_id):
            return True


def run_inline(analysis_id: int) -> None:
    """Para ``inline_worker``: corre el análisis en una tarea de fondo de la API."""
    db = new_session()
    try:
        process_analysis(db, analysis_id)
    finally:
        db.close()


def drain_queue() -> int:
    """Procesa los análisis pendientes hasta vaciar la cola. Devuelve cuántos procesó."""
    processed = 0
    db = new_session()
    try:
        while process_next(db):
            processed += 1
    except Exception:  # un fallo de la base no debe dejar el hilo en un bucle sin fin
        log.exception("La cola se detuvo tras procesar %d análisis", processed)
    finally:
        db.close()
    return processed


def start_inline_drain() -> threading.Thread:
    """Para ``inline_worker``: al arrancar la API, procesa en segundo plano lo que quedó pendiente.

    ``requeue_stale`` devuelve a ``pending`` los análisis interrumpidos, pero en modo inline no
    hay otro proceso que los tome. El hilo es daemon (no frena el cierre de la API) y termina solo
    al vaciar la cola; los análisis nuevos los lanza cada petición con ``run_inline``.
    """

    def run() -> None:
        processed = drain_queue()
        if processed:
            log.info("Cola inline vaciada: %d análisis procesados", processed)

    thread = threading.Thread(target=run, name="ecoaudit-inline-drain", daemon=True)
    thread.start()
    return thread


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    init_db()
    poll = get_settings().worker_poll_seconds
    log.info("Worker iniciado; consultando la cola cada %.1f s", poll)
    while True:
        db = new_session()
        try:
            requeue_stale(db)
            worked = process_next(db)
        finally:
            db.close()
        if not worked:
            time.sleep(poll)


if __name__ == "__main__":
    main()
