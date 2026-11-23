"""Indicadores de actividad, desempeño y concordancia por alcance de casos."""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from itertools import combinations, groupby
from typing import get_args

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..case_access import visible_analysis_result, visible_cases
from ..config import get_settings
from ..db import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    Analysis,
    AnalysisStatus,
    Case,
    ClinicalReading,
    Image,
    ModelVersion,
    Role,
    User,
    utcnow,
)
from ..registry import get_active
from ..reports import DECISION_LABELS
from ..schemas import Birads

router = APIRouter(prefix="/api/stats", tags=["indicadores"])
_research = require_roles(Role.admin, Role.investigador)


def _analyses(query, user: User):
    return visible_cases(query.join(Image, Image.id == Analysis.image_id).join(Case), user)


def _readings(query, user: User):
    query = _analyses(query.join(Analysis, Analysis.id == ClinicalReading.analysis_id), user)
    if user.role != Role.admin:
        query = query.where(ClinicalReading.reader_id == user.id)
    return query


def _latency(values: list[float]) -> dict:
    p50, p95 = np.quantile(values, [0.5, 0.95]).tolist() if values else (None, None)
    return {
        "n": len(values),
        "mean": sum(values) / len(values) if values else None,
        "p50": p50,
        "p95": p95,
        "max": max(values, default=None),
    }


def _duration(start: datetime | None, end: datetime | None, values: list[float]) -> None:
    if start is not None and end is not None:
        values.append((end - start).total_seconds())


@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    today = utcnow().date()
    first_day = today - timedelta(days=29)
    start = datetime.combine(first_day, time.min, UTC)
    end = datetime.combine(today + timedelta(days=1), time.min, UTC)
    days = Counter()
    states = Counter(dict.fromkeys(AnalysisStatus, 0))
    decisions = Counter(dict.fromkeys(DECISION_LABELS, 0))
    shift_alerts = monitored = visible_done = 0
    processing: list[float] = []
    total: list[float] = []
    rows = db.execute(
        _analyses(
            select(
                Analysis.status,
                Analysis.decision,
                Analysis.shift_flag,
                Analysis.created_at,
                Analysis.started_at,
                Analysis.finished_at,
                visible_analysis_result(user).label("result_visible"),
            ),
            user,
        )
    )
    for state, decision, shift, created, started, finished, result_visible in rows:
        states[state] += 1
        if start <= created < end:
            days[created.astimezone(UTC).date()] += 1
        if state == AnalysisStatus.done:
            _duration(started, finished, processing)
            _duration(created, finished, total)
            if result_visible:
                visible_done += 1
                if decision is not None:
                    decisions[decision] += 1
                monitored += shift is not None
                shift_alerts += shift is True
    active = get_active(db)
    return {
        "cases": db.scalar(visible_cases(select(func.count()).select_from(Case), user)),
        "images": db.scalar(
            visible_cases(select(func.count()).select_from(Image).join(Case), user)
        ),
        "analyses_by_status": dict(states),
        "decisions": dict(decisions),
        "abstention_rate": decisions["indeterminate"] / visible_done if visible_done else None,
        "shift_alert_rate": shift_alerts / visible_done if visible_done else None,
        "shift_monitored": monitored,
        "analyses_by_day": [
            {"date": day, "count": days[day]}
            for day in (first_day + timedelta(days=i) for i in range(30))
        ],
        "latency_seconds": {"processing": _latency(processing), "total": _latency(total)},
        "active_model": {"name": active.name, "version": active.version} if active else None,
        "clinical_readings": db.scalar(
            _readings(select(func.count()).select_from(ClinicalReading), user)
        ),
    }


@router.get("/performance")
def performance(db: Session = Depends(get_db), user: User = Depends(_research)) -> dict:
    rows = db.execute(
        _analyses(
            select(
                ModelVersion.id,
                ModelVersion.name,
                ModelVersion.version,
                Analysis.created_at,
                Analysis.started_at,
                Analysis.finished_at,
            )
            .select_from(Analysis)
            .join(ModelVersion, ModelVersion.id == Analysis.model_version_id)
            .where(Analysis.status == AnalysisStatus.done)
            .order_by(ModelVersion.id),
            user,
        )
    )
    durations: dict[tuple[int, str, str], tuple[list[float], list[float]]] = defaultdict(
        lambda: ([], [])
    )
    for model_id, name, version, created, started, finished in rows:
        processing, total = durations[model_id, name, version]
        _duration(started, finished, processing)
        _duration(created, finished, total)
    return {
        "models": [
            {
                "model_version_id": model_id,
                "name": name,
                "version": version,
                "latency_seconds": {"processing": _latency(processing), "total": _latency(total)},
            }
            for (model_id, name, version), (processing, total) in durations.items()
        ]
    }


@router.get("/concordance")
def concordance(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    rows = db.execute(
        _readings(
            select(ClinicalReading.birads, ClinicalReading.blinded, Analysis.decision)
            .select_from(ClinicalReading)
            .where(
                Analysis.status == AnalysisStatus.done,
                Analysis.decision.in_(("probably_benign", "suspicious", "indeterminate")),
            ),
            user,
        )
    )
    birads = Counter(dict.fromkeys(get_args(Birads), 0))
    matrix = [[0, 0], [0, 0]]
    blinded = indeterminate = 0
    for category, blind, decision in rows:
        birads[category] += 1
        blinded += blind
        if decision == "indeterminate":
            indeterminate += 1
        else:
            matrix[int(category not in ("1", "2", "3"))][int(decision == "suspicious")] += 1
    (tn, fp), (fn, tp) = matrix
    binary = tn + fp + fn + tp
    agreement = (tn + tp) / binary if binary else None
    expected = (tn + fp) * (tn + fn) + (fn + tp) * (fp + tp)
    denominator = binary**2 - expected
    return {
        "matrix": matrix,
        "agreement_percent": 100 * agreement if agreement is not None else None,
        "kappa": (binary * (tn + tp) - expected) / denominator if denominator else None,
        "n": binary + indeterminate,
        "n_indeterminate": indeterminate,
        "n_blinded": blinded,
        "n_unblinded": binary + indeterminate - blinded,
        "birads": dict(birads),
    }


def _weighted_kappa(matrix: np.ndarray) -> float | None:
    n = matrix.sum()
    indices = np.arange(len(matrix))
    distances = np.abs(indices[:, None] - indices)
    observed = (matrix * distances).sum()
    expected = (np.outer(matrix.sum(axis=1), matrix.sum(axis=0)) * distances).sum()
    return float(1 - n * observed / expected) if expected else None


@router.get("/inter-reader")
def inter_reader(db: Session = Depends(get_db), user: User = Depends(_research)) -> dict:
    categories = {category: index for index, category in enumerate(get_args(Birads))}
    rows = db.execute(
        _analyses(
            select(ClinicalReading.analysis_id, User.id, User.full_name, ClinicalReading.birads)
            .select_from(ClinicalReading)
            .join(User, User.id == ClinicalReading.reader_id)
            .join(Analysis, Analysis.id == ClinicalReading.analysis_id)
            .where(User.role == Role.medico)
            .order_by(ClinicalReading.analysis_id, User.id),
            user,
        ).execution_options(yield_per=1000)
    )
    matrices = defaultdict(lambda: np.zeros((len(categories), len(categories)), dtype=np.int64))
    names = {}
    n = 0
    for _, group in groupby(rows, key=lambda row: row.analysis_id):
        readings = list(group)
        n += len(readings) >= 2
        for first, second in combinations(readings, 2):
            names[first.id] = first.full_name
            names[second.id] = second.full_name
            matrices[first.id, second.id][categories[first.birads], categories[second.birads]] += 1

    pairs = []
    cutoff = categories["4A"]
    for readers, matrix in sorted(matrices.items()):
        binary = np.array(
            [
                [matrix[:cutoff, :cutoff].sum(), matrix[:cutoff, cutoff:].sum()],
                [matrix[cutoff:, :cutoff].sum(), matrix[cutoff:, cutoff:].sum()],
            ]
        )
        size = int(matrix.sum())
        pairs.append(
            {
                "readers": [{"id": reader, "full_name": names[reader]} for reader in readers],
                "n": size,
                "kappa": _weighted_kappa(binary),
                "weighted_kappa": _weighted_kappa(matrix),
                "agreement_percent": float(100 * matrix.trace() / size),
            }
        )
    return {"n": n, "pairs": pairs}


@dataclass
class _DriftTotals:
    n: int = 0
    alerts: int = 0
    abstentions: int = 0
    score_sum: float = 0.0
    score_count: int = 0


@router.get("/drift")
def drift(db: Session = Depends(get_db), user: User = Depends(_research)) -> dict:
    now = utcnow()
    latest = now.date() - timedelta(days=now.weekday())
    weeks = [latest - timedelta(weeks=i) for i in reversed(range(12))]
    rows = db.execute(
        _analyses(
            select(
                ModelVersion.id,
                ModelVersion.name,
                ModelVersion.version,
                Analysis.finished_at,
                Analysis.shift_flag,
                Analysis.shift_score,
                Analysis.decision,
            )
            .select_from(Analysis)
            .join(ModelVersion, ModelVersion.id == Analysis.model_version_id)
            .where(
                Analysis.status == AnalysisStatus.done,
                Analysis.finished_at >= datetime.combine(weeks[0], time.min, UTC),
                Analysis.finished_at <= now,
                visible_analysis_result(user),
            ),
            user,
        ).execution_options(yield_per=1000)
    )
    threshold = get_settings().drift_alert_rate
    models = {}
    groups = defaultdict(_DriftTotals)
    for model_id, name, version, finished, flag, score, decision in rows:
        models[model_id] = (name, version)
        week = finished.date() - timedelta(days=finished.weekday())
        totals = groups[model_id, week]
        totals.n += 1
        totals.alerts += flag is True
        totals.abstentions += decision in ("indeterminate", "out_of_domain")
        if score is not None:
            totals.score_sum += score
            totals.score_count += 1
    series = []
    for model_id, (name, version) in sorted(models.items()):
        points = []
        for week in weeks:
            totals = groups[model_id, week]
            n = totals.n
            rate = totals.alerts / n if n else None
            points.append(
                {
                    "week": week,
                    "n": n,
                    "shift_alert_rate": rate,
                    "mean_shift_score": totals.score_sum / totals.score_count
                    if totals.score_count
                    else None,
                    "abstention_rate": totals.abstentions / n if n else None,
                    "alert": week == latest and n >= 10 and rate is not None and rate > threshold,
                }
            )
        series.append(
            {"model_version_id": model_id, "name": name, "version": version, "weeks": points}
        )
    return {"weeks": weeks, "alert_threshold": threshold, "models": series}
