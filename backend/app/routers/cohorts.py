"""Cohortes de auditoría: análisis con etiqueta binaria y las métricas que resultan.

Hay dos orígenes. ``POST /api/cohorts`` toma análisis que el investigador ya tiene terminados
(CSV ``analysis_id,label``). ``POST /api/cohorts/batch`` recibe un lote nuevo de imágenes con su
manifiesto, lo carga y encola un análisis por imagen; el worker cierra la cohorte al terminar el
último. Un investigador solo ve sus cohortes; el administrador, todas.
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from starlette.datastructures import UploadFile as StarletteUploadFile

from ..cohorts import Entry, build_results, paired_auc_difference, progress, refresh_cohort
from ..cohorts import summarize as summarize  # noqa: F401  (reexportada: ``tests`` la importa de aquí)
from ..config import get_settings
from ..db import get_db
from ..deps import record, require_roles
from ..models import (
    Analysis,
    AnalysisStatus,
    Case,
    Cohort,
    CohortItem,
    CohortSource,
    CohortStatus,
    Image,
    ModelVersion,
    Role,
    User,
    utcnow,
)
from ..pipeline.imaging import ImageDecodeError
from ..registry import get_active
from ..reports import DECISION_LABELS, pdf
from ..schemas import CohortDetail, CohortMetrics, CohortProgress, CohortReanalyze, CohortSummary
from ..services import DuplicateFinder, PreparedImage, prepare_image, store_image
from ..storage import get_storage
from ..worker import run_inline

router = APIRouter(prefix="/api/cohorts", tags=["cohortes"])
_research = require_roles(Role.admin, Role.investigador)

MAX_CSV_BYTES = 256_000
MAX_CSV_ROWS = 5000  # cohorte desde análisis existentes
MAX_BATCH_IMAGES = 1000
MAX_NAME_LENGTH = 120
MAX_PROBLEMS_SHOWN = 10
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


# ---------------------------------------------------------------- acceso y salida
def _cohort_or_404(db: Session, cohort_id: int, user: User) -> Cohort:
    cohort = db.get(Cohort, cohort_id)
    # 404 y no 403: no se revela la existencia de cohortes ajenas.
    if cohort is None or (user.role != Role.admin and cohort.owner_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cohorte no encontrada.")
    return cohort


def _summary(cohort: Cohort, counts: dict[str, int]) -> CohortSummary:
    model = cohort.model_version
    return CohortSummary(
        id=cohort.id,
        name=cohort.name,
        source=cohort.source,
        status=cohort.status,
        model=f"{model.name} {model.version}",
        created_at=cohort.created_at,
        progress=CohortProgress(**counts),
    )


def _detail(db: Session, cohort: Cohort) -> CohortDetail:
    counts = progress(db, [cohort.id])[cohort.id]
    return CohortDetail(
        **_summary(cohort, counts).model_dump(),
        results=CohortMetrics.model_validate(cohort.results) if cohort.results else None,
        error=cohort.error,
    )


def _clean_name(name: str, default: str | None = None) -> str:
    name = name.strip()
    if not name:
        if default is None:
            raise HTTPException(422, "El nombre de la cohorte es obligatorio.")
        return default
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(422, f"El nombre no puede superar {MAX_NAME_LENGTH} caracteres.")
    return name


def _invalid(problems: list[str]) -> HTTPException:
    """422 con los primeros problemas del lote en un solo mensaje."""
    shown = problems[:MAX_PROBLEMS_SHOWN]
    extra = len(problems) - len(shown)
    detail = " ".join(shown) + (f" (y {extra} problemas más)" if extra > 0 else "")
    return HTTPException(422, detail)


# ---------------------------------------------------------------- listado y detalle
@router.get("", response_model=list[CohortSummary])
def list_cohorts(
    db: Session = Depends(get_db), user: User = Depends(_research)
) -> list[CohortSummary]:
    query = select(Cohort).options(joinedload(Cohort.model_version)).order_by(Cohort.id.desc())
    if user.role != Role.admin:
        query = query.where(Cohort.owner_id == user.id)
    cohorts = list(db.scalars(query))
    counts = progress(db, [c.id for c in cohorts])
    return [_summary(c, counts[c.id]) for c in cohorts]


def _paired_rows(db: Session, cohort: Cohort):
    return db.execute(
        select(
            Analysis.image_id,
            CohortItem.patient_ref,
            CohortItem.label,
            Analysis.probability,
            Analysis.decision,
            Analysis.shift_flag,
        )
        .join(Analysis, Analysis.id == CohortItem.analysis_id)
        .where(CohortItem.cohort_id == cohort.id)
        .order_by(CohortItem.id)
    ).all()


def _comparison_metrics(cohort: Cohort, rows) -> dict:
    return {
        "cohort_id": cohort.id,
        "model_version_id": cohort.model_version_id,
        "auc": cohort.results["auc"],
        "ci": cohort.results["ci"],
        "brier": cohort.results["brier"],
        "abstention_rate": cohort.results["abstentions"] / len(rows),
        "shift_alert_rate": sum(row.shift_flag is True for row in rows) / len(rows),
        "shift_monitored": sum(row.shift_flag is not None for row in rows),
    }


@router.get("/compare")
def compare_cohorts(
    a: int,
    b: int,
    db: Session = Depends(get_db),
    user: User = Depends(_research),
) -> dict:
    first, second = _cohort_or_404(db, a, user), _cohort_or_404(db, b, user)
    for cohort in (first, second):
        refresh_cohort(db, cohort)
        if cohort.status != CohortStatus.done or not cohort.results:
            raise HTTPException(409, "Ambas cohortes deben tener resultados.")
    rows_a, rows_b = _paired_rows(db, first), _paired_rows(db, second)
    keys_a = Counter((row.image_id, row.patient_ref, row.label) for row in rows_a)
    keys_b = Counter((row.image_id, row.patient_ref, row.label) for row in rows_b)
    if not keys_a or keys_a != keys_b:
        raise HTTPException(409, "Las cohortes deben compartir imágenes, pacientes y etiquetas.")
    if any(row.probability is None for rows in (rows_a, rows_b) for row in rows):
        raise HTTPException(409, "Faltan probabilidades en las cohortes.")
    entries_a = [Entry(row.patient_ref, row.label, row.probability, row.decision) for row in rows_a]
    entries_b = [Entry(row.patient_ref, row.label, row.probability, row.decision) for row in rows_b]
    return {
        "a": _comparison_metrics(first, rows_a),
        "b": _comparison_metrics(second, rows_b),
        "paired_auc_difference": paired_auc_difference(entries_a, entries_b),
    }


@router.get("/{cohort_id}", response_model=CohortDetail)
def get_cohort(
    cohort_id: int, db: Session = Depends(get_db), user: User = Depends(_research)
) -> CohortDetail:
    cohort = _cohort_or_404(db, cohort_id, user)
    refresh_cohort(db, cohort)  # si ya terminaron todos los análisis, calcula el resultado
    return _detail(db, cohort)


@router.post("/{cohort_id}/reanalyze", response_model=CohortDetail, status_code=201)
def reanalyze(
    cohort_id: int,
    body: CohortReanalyze,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_research),
) -> CohortDetail:
    source = _cohort_or_404(db, cohort_id, user)
    model = db.get(ModelVersion, body.model_version_id)
    if model is None:
        raise HTTPException(404, "Versión de modelo no encontrada.")
    query = (
        select(
            CohortItem.patient_ref,
            CohortItem.label,
            Analysis.image_id,
            Analysis.roi,
            Case.created_by_id,
        )
        .join(Analysis, Analysis.id == CohortItem.analysis_id)
        .join(Image, Image.id == Analysis.image_id)
        .join(Case, Case.id == Image.case_id)
        .where(CohortItem.cohort_id == source.id)
        .order_by(CohortItem.id)
    )
    rows = db.execute(query).all()
    if user.role != Role.admin and any(row.created_by_id != user.id for row in rows):
        raise HTTPException(404, "Cohorte no encontrada.")
    if not rows:
        raise HTTPException(409, "La cohorte está vacía.")
    suffix = f" · {model.version}"
    cohort = Cohort(
        name=source.name[: MAX_NAME_LENGTH - len(suffix)] + suffix,
        source=CohortSource.batch,
        status=CohortStatus.processing,
        owner_id=user.id,
        model_version_id=model.id,
        csv_hash=source.csv_hash,
    )
    db.add(cohort)
    analyses = []
    for row in rows:
        analysis = Analysis(
            image_id=row.image_id, roi=row.roi, model_version_id=model.id, requested_by_id=user.id
        )
        analyses.append(analysis)
        cohort.items.append(
            CohortItem(analysis=analysis, patient_ref=row.patient_ref, label=row.label)
        )
    db.flush()
    record(
        db,
        user,
        "cohort_reanalyzed",
        "cohort",
        cohort.id,
        source_cohort_id=source.id,
        model_version_id=model.id,
    )
    db.commit()
    if get_settings().inline_worker:
        for analysis in analyses:
            background.add_task(run_inline, analysis.id)
    return _detail(db, cohort)


# ---------------------------------------------------------------- desde análisis existentes
def _read_analyses(
    db: Session, user: User, data: bytes
) -> tuple[ModelVersion, list[tuple[Analysis, str, int]]]:
    """Lee y valida el CSV ``analysis_id,label``. Devuelve el modelo común y, por fila, el
    análisis, el seudónimo del paciente y la etiqueta. Lanza ``ValueError`` con un mensaje en
    español si algo no cumple."""
    rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), strict=True)
    if rows.fieldnames != ["analysis_id", "label"]:
        raise ValueError("La cabecera debe ser analysis_id,label.")
    entries: list[tuple[Analysis, str, int]] = []
    owners: dict[str, int] = {}
    labels: dict[str, int] = {}
    pixels: set[str] = set()
    version: ModelVersion | None = None
    for line, row in enumerate(rows, 2):
        if line > MAX_CSV_ROWS + 1 or None in row or row["label"] not in ("0", "1"):
            raise ValueError(f"Fila {line} inválida o límite de {MAX_CSV_ROWS} imágenes superado.")
        try:
            ident = int(row["analysis_id"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Identificador inválido en fila {line}.") from exc
        analysis = db.get(Analysis, ident) if 0 < ident < 2**63 else None
        case = analysis.image.case if analysis is not None else None
        # Mismo mensaje si no existe, si es ajeno o si no terminó: no se revela cuál de los tres.
        if (
            analysis is None
            or analysis.status != AnalysisStatus.done
            or (user.role != Role.admin and case.created_by_id != user.id)
        ):
            raise ValueError(f"Falta un análisis terminado en la fila {line}.")
        if version is not None and version.id != analysis.model_version_id:
            raise ValueError(
                f"Todos los análisis deben usar la misma versión de modelo (fila {line})."
            )
        version = analysis.model_version
        if analysis.image.pixel_sha256 in pixels:
            raise ValueError(f"Imagen repetida en la fila {line}. Revise su procedencia.")
        pixels.add(analysis.image.pixel_sha256)
        patient_ref = case.patient_ref.strip()
        if (
            not patient_ref
            or owners.setdefault(patient_ref, case.created_by_id) != case.created_by_id
        ):
            raise ValueError("Seudónimo vacío o compartido por distintos responsables.")
        label = int(row["label"])
        if labels.setdefault(patient_ref, label) != label:
            raise ValueError(f"Etiquetas incompatibles para un paciente en la fila {line}.")
        entries.append((analysis, patient_ref, label))
    if version is None:
        raise ValueError("El CSV no tiene filas.")
    return version, entries


@router.post("", response_model=CohortDetail, status_code=status.HTTP_201_CREATED)
def create_from_analyses(
    file: UploadFile,
    name: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(_research),
) -> CohortDetail:
    cohort_name = _clean_name(name, default=f"Cohorte {utcnow():%Y-%m-%d %H:%M} UTC")
    data = file.file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(413, "El CSV supera 256 kB.")
    csv_hash = hashlib.sha256(data).hexdigest()
    try:
        version, entries = _read_analyses(db, user, data)
        results = build_results(
            version,
            csv_hash,
            [Entry(ref, label, a.probability, a.decision) for a, ref, label in entries],
        )
    except (ValueError, csv.Error) as exc:
        raise HTTPException(422, str(exc)) from exc

    cohort = Cohort(
        name=cohort_name,
        source=CohortSource.analyses,
        status=CohortStatus.done,
        owner_id=user.id,
        model_version_id=version.id,
        csv_hash=csv_hash,
        results=results,
        finished_at=utcnow(),
    )
    cohort.items = [
        CohortItem(analysis_id=a.id, patient_ref=ref, label=label) for a, ref, label in entries
    ]
    db.add(cohort)
    db.flush()
    record(db, user, "cohort_created", "cohort", cohort.id)
    db.commit()
    return _detail(db, cohort)


# ---------------------------------------------------------------- lote nuevo
def _basename(name: str) -> str:
    """Nombre de archivo sin carpetas (algunos navegadores envían la ruta relativa)."""
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip()


def _read_manifest(data: bytes) -> list[tuple[int, str, str, int]]:
    """Lee ``filename,patient_ref,label``. Devuelve ``(fila, archivo, paciente, etiqueta)``.
    Lanza ``HTTPException`` 422 con todos los problemas de las filas."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "El manifiesto debe estar codificado en UTF-8.") from exc
    reader = csv.DictReader(io.StringIO(text), strict=True)
    try:
        if reader.fieldnames != ["filename", "patient_ref", "label"]:
            raise HTTPException(
                422, "La cabecera del manifiesto debe ser filename,patient_ref,label."
            )
        problems: list[str] = []
        rows: list[tuple[int, str, str, int]] = []
        names: dict[str, int] = {}
        patient_labels: dict[str, tuple[int, int]] = {}  # paciente -> (etiqueta, fila)
        for line, row in enumerate(reader, 2):
            if line > MAX_BATCH_IMAGES + 1:
                raise HTTPException(
                    422, f"El manifiesto supera el límite de {MAX_BATCH_IMAGES} imágenes."
                )
            if None in row or None in row.values():
                problems.append(
                    f"Fila {line} del manifiesto: debe tener exactamente tres columnas."
                )
                continue
            filename = _basename(row["filename"])
            patient_ref = row["patient_ref"].strip()
            if not filename:
                problems.append(f"Fila {line} del manifiesto: falta el nombre del archivo.")
            if not patient_ref or len(patient_ref) > 64:
                problems.append(
                    f"Fila {line} del manifiesto: patient_ref debe tener de 1 a 64 caracteres."
                )
            if row["label"].strip() not in ("0", "1"):
                problems.append(f"Fila {line} del manifiesto: label debe ser 0 o 1.")
                continue
            label = int(row["label"].strip())
            if filename and filename in names:
                problems.append(
                    f"Fila {line} del manifiesto: «{filename}» ya figura en la fila {names[filename]}."
                )
            names.setdefault(filename, line)
            if patient_ref:
                first_label, first_line = patient_labels.setdefault(patient_ref, (label, line))
                if first_label != label:
                    problems.append(
                        f"Fila {line} del manifiesto: etiqueta distinta a la de la fila {first_line} "
                        f"para el paciente «{patient_ref}»."
                    )
            rows.append((line, filename, patient_ref, label))
    except csv.Error as exc:
        raise HTTPException(422, f"Manifiesto mal formado: {exc}") from exc
    if problems:
        raise _invalid(problems)
    if not rows:
        raise HTTPException(422, "El manifiesto no tiene filas.")
    patient_classes = {label for label, _ in patient_labels.values()}
    if patient_classes != {0, 1}:
        raise HTTPException(422, "Se necesita al menos un paciente de cada clase (0 y 1).")
    return rows


def _prepare_batch(
    rows: list[tuple[int, str, str, int]], images: list[UploadFile]
) -> dict[str, PreparedImage]:
    """Comprueba que los archivos coincidan con el manifiesto y decodifica cada imagen.
    No escribe nada. Lanza ``HTTPException`` 422 con todos los problemas encontrados."""
    uploaded: dict[str, UploadFile] = {}
    problems: list[str] = []
    for upload in images:
        name = _basename(upload.filename or "")
        if not name:
            problems.append("Hay un archivo sin nombre.")
        elif name in uploaded:
            problems.append(f"El archivo «{name}» se envió más de una vez.")
        else:
            uploaded[name] = upload
    listed = {filename for _, filename, _, _ in rows}
    missing = sorted(listed - uploaded.keys())
    extra = sorted(uploaded.keys() - listed)
    if missing:
        problems.append("Faltan archivos del manifiesto: " + _names(missing) + ".")
    if extra:
        problems.append("Archivos que no figuran en el manifiesto: " + _names(extra) + ".")
    if problems:
        raise _invalid(problems)

    limit = get_settings().max_upload_mb * 1024 * 1024
    prepared: dict[str, PreparedImage] = {}
    by_hash: dict[str, str] = {}
    for _, filename, _, _ in rows:
        data = uploaded[filename].file.read(limit + 1)
        if len(data) > limit:
            problems.append(f"«{filename}» supera {get_settings().max_upload_mb} MB.")
            continue
        try:
            image = prepare_image(data, filename)
        except ImageDecodeError as exc:
            problems.append(f"«{filename}»: {exc}")
            continue
        if image.pixel_sha256 in by_hash:
            problems.append(
                f"«{filename}» es idéntica a «{by_hash[image.pixel_sha256]}». "
                "Un lote no admite imágenes repetidas."
            )
            continue
        by_hash[image.pixel_sha256] = filename
        prepared[filename] = image
    if problems:
        raise _invalid(problems)
    return prepared


def _names(names: list[str]) -> str:
    shown = ", ".join(f"«{n}»" for n in names[:5])
    return shown + (f" y {len(names) - 5} más" if len(names) > 5 else "")


# Starlette limita por defecto a 1000 los archivos de un formulario (y con otro mensaje y código)
# y un lote de 1000 imágenes lleva además el manifiesto. Se lee el formulario con un tope propio
# para poder responder con el 422 del contrato, y el trabajo pesado corre en un hilo aparte.
MAX_FORM_FILES = 2 * MAX_BATCH_IMAGES + 1
_BATCH_BODY = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["name", "manifest", "images"],
                "properties": {
                    "name": {"type": "string", "maxLength": MAX_NAME_LENGTH},
                    "manifest": {"type": "string", "format": "binary"},
                    "images": {"type": "array", "items": {"type": "string", "format": "binary"}},
                },
            }
        }
    },
}


@router.post(
    "/batch",
    response_model=CohortDetail,
    status_code=status.HTTP_201_CREATED,
    openapi_extra={"requestBody": _BATCH_BODY},
)
async def create_batch(
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_research),
) -> CohortDetail:
    try:
        form = await request.form(max_files=MAX_FORM_FILES, max_fields=100)
    except HTTPException as exc:  # formulario mal formado o por encima de los límites
        raise HTTPException(
            422, f"El envío no es válido o supera el límite de {MAX_BATCH_IMAGES} imágenes."
        ) from exc
    try:
        name = form.get("name")
        manifest = form.get("manifest")
        return await run_in_threadpool(
            _create_batch,
            db,
            user,
            background,
            name if isinstance(name, str) else "",
            manifest if isinstance(manifest, StarletteUploadFile) else None,
            [f for f in form.getlist("images") if isinstance(f, StarletteUploadFile)],
        )
    finally:
        await form.close()


def _create_batch(
    db: Session,
    user: User,
    background: BackgroundTasks,
    name: str,
    manifest: UploadFile | None,
    images: list[UploadFile],
) -> CohortDetail:
    model = get_active(db)
    if model is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No hay un modelo activo. Un administrador debe registrar y activar uno.",
        )
    cohort_name = _clean_name(name)
    if manifest is None:
        raise HTTPException(422, "Falta el manifiesto CSV (filename,patient_ref,label).")
    manifest_data = manifest.file.read(MAX_CSV_BYTES + 1)
    if len(manifest_data) > MAX_CSV_BYTES:
        raise HTTPException(413, "El manifiesto supera 256 kB.")
    if len(images) > MAX_BATCH_IMAGES:
        raise HTTPException(422, f"El lote supera el límite de {MAX_BATCH_IMAGES} imágenes.")

    # Todo se valida antes de escribir nada.
    rows = _read_manifest(manifest_data)
    prepared = _prepare_batch(rows, images)

    # Después se crea todo en una transacción. Los archivos del almacén no son transaccionales:
    # si algo falla se revierte la base y se borran los que ya se escribieron.
    storage = get_storage()
    written: list[str] = []
    try:
        cohort = Cohort(
            name=cohort_name,
            source=CohortSource.batch,
            status=CohortStatus.processing,
            owner_id=user.id,
            model_version_id=model.id,
            csv_hash=hashlib.sha256(manifest_data).hexdigest(),
        )
        db.add(cohort)
        cases: dict[str, Case] = {}
        analyses: list[Analysis] = []
        finder = DuplicateFinder(db, user.id)
        for _, filename, patient_ref, label in rows:
            case = cases.get(patient_ref)
            if case is None:
                case = cases[patient_ref] = Case(patient_ref=patient_ref, created_by_id=user.id)
                db.add(case)
                db.flush()
            image = store_image(db, case, prepared[filename], finder)
            written.append(image.storage_key)
            analysis = Analysis(
                image_id=image.id, requested_by_id=user.id, model_version_id=model.id, roi=None
            )
            analyses.append(analysis)
            cohort.items.append(CohortItem(analysis=analysis, patient_ref=patient_ref, label=label))
        db.flush()
        record(db, user, "cohort_created", "cohort", cohort.id)
        db.commit()
    except Exception:
        db.rollback()
        for key in written:
            storage.delete(key)
        raise
    if get_settings().inline_worker:
        for analysis in analyses:
            background.add_task(run_inline, analysis.id)
    return _detail(db, cohort)


# ---------------------------------------------------------------- informe y tabla
@router.get("/{cohort_id}/report")
def report(cohort_id: int, db: Session = Depends(get_db), user: User = Depends(_research)):
    cohort = _cohort_or_404(db, cohort_id, user)
    refresh_cohort(db, cohort)
    if cohort.status != CohortStatus.done or not cohort.results:
        raise HTTPException(status.HTTP_409_CONFLICT, "La cohorte aún no tiene resultados.")
    r = cohort.results
    model = cohort.model_version
    interval = " a ".join(f"{v:.3f}" for v in r["ci"]) if r["ci"] else "no estimable"
    decisions = "; ".join(
        f"{DECISION_LABELS.get(code, code)}: {n}" for code, n in sorted(r["decisions"].items())
    )
    csv_label = (
        "SHA-256 del CSV" if cohort.source == CohortSource.analyses else "SHA-256 del manifiesto"
    )
    return pdf(
        f"Auditoría de cohorte {cohort.id}",
        [
            ("Cohorte", cohort.name),
            ("Modelo", f"{model.name} {model.version}" + (" (demostración)" if r["demo"] else "")),
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
            ("Decisiones", decisions or "Ninguna registrada"),
            (
                "Método",
                "Media de logits calibrados por paciente. IC percentil con 1000 remuestreos estratificados por clase, semilla 42.",
            ),
            ("SHA-256 del modelo", r["model_hash"]),
            (csv_label, r["csv_hash"]),
        ],
    )


def _csv_cell(value: str) -> str:
    """Evita que una hoja de cálculo interprete como fórmula un seudónimo escrito por el usuario."""
    return "'" + value if value.startswith(_FORMULA_PREFIXES) else value


@router.get("/{cohort_id}/items.csv")
def items_csv(cohort_id: int, db: Session = Depends(get_db), user: User = Depends(_research)):
    cohort = _cohort_or_404(db, cohort_id, user)
    rows = db.execute(
        select(CohortItem, Analysis)
        .join(Analysis, Analysis.id == CohortItem.analysis_id)
        .where(CohortItem.cohort_id == cohort.id)
        .order_by(CohortItem.id)
    )
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["analysis_id", "patient_ref", "label", "probability", "decision", "status"])
    for item, analysis in rows:
        writer.writerow(
            [
                analysis.id,
                _csv_cell(item.patient_ref),
                item.label,
                "" if analysis.probability is None else analysis.probability,
                analysis.decision or "",
                analysis.status.value,
            ]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="cohorte-{cohort.id}-items.csv"',
            "Cache-Control": "no-store",
        },
    )
