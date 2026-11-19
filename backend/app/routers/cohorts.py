"""Auditoría de análisis terminados con etiquetas binarias aportadas por el investigador."""

import csv
import hashlib
import io

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import record, require_roles
from ..models import Analysis, AnalysisStatus, AuditLog, Role, User
from ..reports import pdf

router = APIRouter(prefix="/api/cohorts", tags=["auditoría"])
_research = require_roles(Role.admin, Role.investigador)


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


@router.post("")
def audit(file: UploadFile, db: Session = Depends(get_db), user: User = Depends(_research)):
    data = file.file.read(256001)
    if len(data) > 256000:
        raise HTTPException(413, "El CSV supera 256 kB.")
    groups, owners, pixels = {}, {}, set()
    version = None
    abstentions = 0
    try:
        rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        if rows.fieldnames != ["analysis_id", "label"]:
            raise ValueError("La cabecera debe ser analysis_id,label.")
        for line, row in enumerate(rows, 2):
            if line > 5001 or None in row or row["label"] not in ("0", "1"):
                raise ValueError(f"Fila {line} inválida o límite de 5000 imágenes superado.")
            try:
                ident = int(row["analysis_id"])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Identificador inválido en fila {line}.") from exc
            a = db.get(Analysis, ident) if 0 < ident < 2**63 else None
            if a is None or a.status != AnalysisStatus.done:
                raise ValueError(f"Falta un análisis terminado en la fila {line}.")
            if version and version.id != a.model_version_id:
                raise ValueError("Todos los análisis deben usar la misma versión de modelo.")
            version = a.model_version
            image = a.image
            if image.pixel_sha256 in pixels:
                raise ValueError(f"Imagen repetida en la fila {line}. Revise su procedencia.")
            pixels.add(image.pixel_sha256)
            case = image.case
            key = case.patient_ref.strip()
            if not key or owners.setdefault(key, case.created_by_id) != case.created_by_id:
                raise ValueError("Seudónimo vacío o compartido por distintos responsables.")
            label, probs = groups.setdefault(key, (int(row["label"]), []))
            if label != int(row["label"]):
                raise ValueError(f"Etiquetas incompatibles para un paciente en la fila {line}.")
            probs.append(a.probability)
            abstentions += a.decision in ("out_of_domain", "indeterminate")
        result = summarize(groups)
    except (ValueError, csv.Error) as exc:
        raise HTTPException(422, str(exc)) from exc
    result.update(
        images=len(pixels),
        abstentions=abstentions,
        model=f"{version.name} {version.version}",
        demo=bool(version.card.get("demo")),
        model_hash=version.bundle_sha256,
        csv_hash=hashlib.sha256(data).hexdigest(),
    )
    entry = record(db, user, "cohort_evaluated", "cohort", **result)
    db.commit()
    return dict(id=entry.id, **result)


@router.get("/{audit_id}/report")
def report(audit_id: int, db: Session = Depends(get_db), user: User = Depends(_research)):
    entry = db.get(AuditLog, audit_id)
    if (
        not entry
        or entry.action != "cohort_evaluated"
        or (user.role != Role.admin and entry.user_id != user.id)
    ):
        raise HTTPException(404, "Auditoría no encontrada.")
    r = entry.detail
    interval = " a ".join(f"{v:.3f}" for v in r["ci"]) if r["ci"] else "no estimable"
    return pdf(
        f"Auditoría de cohorte {entry.id}",
        [
            ("Modelo", r["model"] + (" (demostración)" if r["demo"] else "")),
            (
                "Pacientes e imágenes",
                f"{r['patients']} pacientes, {r['positive']} positivos, {r['images']} imágenes.",
            ),
            ("Discriminación", f"AUROC {r['auc']:.3f}. IC 95 % {interval}."),
            (
                "Calibración",
                f"Brier {r['brier']:.3f}. ECE {r['ece']:.3f} con diez intervalos uniformes.",
            ),
            (
                "Abstenciones",
                f"{r['abstentions']} imágenes entre indeterminadas y fuera de dominio. Todas se incluyen.",
            ),
            (
                "Método",
                "Media de logits calibrados por paciente. IC percentil con 1000 remuestreos estratificados por clase, semilla 42.",
            ),
            ("SHA-256 del modelo", r["model_hash"]),
            ("SHA-256 del CSV", r["csv_hash"]),
        ],
    )
