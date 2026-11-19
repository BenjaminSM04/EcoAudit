"""Métricas de cohorte y cierre de cohortes en proceso.

Sin dependencias de HTTP: lo usan el router (``routers/cohorts.py``) y el worker.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .models import (
    Analysis,
    AnalysisStatus,
    Cohort,
    CohortItem,
    CohortStatus,
    ModelVersion,
    utcnow,
)

# Decisiones que cuentan como abstención en la auditoría.
ABSTENTIONS = ("out_of_domain", "indeterminate")


def auc(positive, negative):
    ordered = np.sort(negative)
    below = np.searchsorted(ordered, positive, side="left")
    through = np.searchsorted(ordered, positive, side="right")
    return float(np.mean((below + through) / (2 * len(negative))))


def summarize(groups):
    labels, scores = [], []
    for label, probabilities in groups.values():
        p = np.clip(probabilities, 1e-15, 1 - 1e-15)
        logit = np.mean(np.log(p) - np.log1p(-p))
        labels.append(label)
        scores.append(1 / (1 + np.exp(-logit)))
    y, p = np.array(labels), np.array(scores)
    pos, neg = np.sort(p[y == 1]), np.sort(p[y == 0])
    if not len(pos) or not len(neg):
        raise ValueError("Se necesita al menos un paciente de cada clase.")
    rng = np.random.default_rng(42)
    ci = None
    if min(len(pos), len(neg)) >= 2:
        samples = [auc(rng.choice(pos, len(pos)), rng.choice(neg, len(neg))) for _ in range(1000)]
        ci = np.quantile(samples, [0.025, 0.975]).tolist()
    bins = np.minimum((p * 10).astype(int), 9)
    calibration = []
    for i in np.unique(bins):
        use = bins == i
        calibration.append(
            dict(
                bin=int(i),
                n=int(use.sum()),
                predicted=float(p[use].mean()),
                observed=float(y[use].mean()),
            )
        )
    ece = sum(b["n"] * abs(b["predicted"] - b["observed"]) for b in calibration) / len(p)
    return dict(
        patients=len(y),
        positive=len(pos),
        auc=auc(pos, neg),
        ci=ci,
        brier=float(np.mean((p - y) ** 2)),
        ece=ece,
        bins=calibration,
    )


@dataclass(frozen=True)
class Entry:
    """Un análisis terminado de la cohorte, listo para calcular métricas."""

    patient_ref: str
    label: int
    probability: float
    decision: str | None


def build_results(model: ModelVersion, csv_hash: str, entries: list[Entry]) -> dict:
    """Métricas de la cohorte: ``summarize`` por paciente más imágenes, abstenciones y decisiones.

    Lanza ``ValueError`` si no hay al menos un paciente de cada clase.
    """
    groups: dict[str, tuple[int, list[float]]] = {}
    for entry in entries:
        groups.setdefault(entry.patient_ref, (entry.label, []))[1].append(entry.probability)
    result = summarize(groups)
    result.update(
        images=len(entries),
        abstentions=sum(e.decision in ABSTENTIONS for e in entries),
        decisions=dict(Counter(e.decision for e in entries if e.decision)),
        demo=bool(model.card.get("demo")),
        model_hash=model.bundle_sha256,
        csv_hash=csv_hash,
    )
    return result


def progress(db: Session, cohort_ids: list[int]) -> dict[int, dict[str, int]]:
    """Avance de cada cohorte (``total``, ``done``, ``failed``) con una sola consulta."""
    result = {i: {"total": 0, "done": 0, "failed": 0} for i in cohort_ids}
    if not cohort_ids:
        return result
    rows = db.execute(
        select(CohortItem.cohort_id, Analysis.status, func.count())
        .join(Analysis, Analysis.id == CohortItem.analysis_id)
        .where(CohortItem.cohort_id.in_(cohort_ids))
        .group_by(CohortItem.cohort_id, Analysis.status)
    )
    for cohort_id, state, count in rows:
        result[cohort_id]["total"] += count
        if state == AnalysisStatus.done:
            result[cohort_id]["done"] += count
        elif state == AnalysisStatus.failed:
            result[cohort_id]["failed"] += count
    return result


def refresh_cohort(db: Session, cohort: Cohort) -> Cohort:
    """Cierra la cohorte si todos sus análisis terminaron.

    Si alguno falló, la cohorte queda ``failed``; si no, se calculan los resultados. Mientras
    quede algún análisis pendiente o en curso no cambia nada. Es seguro llamarla varias veces y
    desde varios procesos: el cambio de estado es un UPDATE condicionado a ``processing``.
    """
    db.refresh(cohort)
    if cohort.status != CohortStatus.processing:
        return cohort
    rows = db.execute(
        select(
            CohortItem.patient_ref,
            CohortItem.label,
            Analysis.status,
            Analysis.probability,
            Analysis.decision,
        )
        .join(Analysis, Analysis.id == CohortItem.analysis_id)
        .where(CohortItem.cohort_id == cohort.id)
        .order_by(CohortItem.id)
    ).all()
    if any(r.status in (AnalysisStatus.pending, AnalysisStatus.running) for r in rows):
        return cohort

    failed = sum(r.status == AnalysisStatus.failed for r in rows)
    changes: dict
    if failed or not rows:
        changes = dict(status=CohortStatus.failed, results=None)
        changes["error"] = f"{failed} análisis fallaron." if failed else "La cohorte está vacía."
    else:
        entries = [Entry(r.patient_ref, r.label, r.probability, r.decision) for r in rows]
        try:
            results = build_results(cohort.model_version, cohort.csv_hash, entries)
        except ValueError as exc:
            changes = dict(status=CohortStatus.failed, results=None, error=str(exc))
        else:
            changes = dict(status=CohortStatus.done, results=results, error=None)
    db.execute(
        update(Cohort)
        .where(Cohort.id == cohort.id, Cohort.status == CohortStatus.processing)
        .values(finished_at=utcnow(), **changes)
    )
    db.commit()
    db.refresh(cohort)
    return cohort


def refresh_cohorts_of(db: Session, analysis_id: int) -> None:
    """Refresca las cohortes en proceso que incluyen el análisis (lo llama el worker)."""
    cohorts = db.scalars(
        select(Cohort)
        .join(CohortItem, CohortItem.cohort_id == Cohort.id)
        .where(CohortItem.analysis_id == analysis_id, Cohort.status == CohortStatus.processing)
        .distinct()
    ).all()
    for cohort in cohorts:
        refresh_cohort(db, cohort)
