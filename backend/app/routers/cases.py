"""Casos, imágenes, análisis y lecturas asignadas."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..case_access import has_read_analysis, manages_case, visible_cases
from ..config import get_settings
from ..db import get_db
from ..deps import record, require_roles
from ..fhir import analysis_bundle
from ..models import Analysis, AnalysisStatus, Case, CaseReader, ClinicalReading, Image, Role, User
from ..pipeline.imaging import ImageDecodeError
from ..pipeline.localizer import propose
from ..pipeline.runner import RoiError, resolve_roi
from ..registry import get_active
from ..reports import DECISION_LABELS, pdf
from ..schemas import (
    AnalysisCreate,
    AnalysisOut,
    CaseCreate,
    CaseOut,
    CaseReaderInput,
    CaseReaderOut,
    CaseReadersOut,
    CaseSummary,
    ClinicalReadingCreate,
    ClinicalReadingOut,
    ImageOut,
    ReaderIdentity,
    WorklistItem,
)
from ..services import DuplicateFinder, prepare_image, store_image
from ..storage import get_storage
from ..worker import run_inline

router = APIRouter(prefix="/api", tags=["cases"])
_clinical = require_roles(Role.medico, Role.investigador, Role.admin)
_PNG_HEADERS = {"Cache-Control": "private, max-age=3600"}


# ---------------------------------------------------------------- acceso
def _case_or_404(db: Session, case_id: int, user: User, *, manage: bool = False) -> Case:
    case = db.get(Case, case_id)
    # 404 y no 403: no se revela la existencia de casos ajenos.
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado.")
    if manages_case(case, user):
        return case
    if user.role != Role.medico or db.get(CaseReader, (case_id, user.id)) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado.")
    if manage:
        raise HTTPException(
            403, "La asignación solo permite consultar el caso y registrar lecturas."
        )
    return case


def _image_or_404(db: Session, image_id: int, user: User, *, manage: bool = False) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada.")
    _case_or_404(db, image.case_id, user, manage=manage)
    return image


def _analysis_or_404(db: Session, analysis_id: int, user: User) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análisis no encontrado.")
    _image_or_404(db, analysis.image_id, user)
    return analysis


# ---------------------------------------------------------------- salida
def _analysis_out(
    analysis: Analysis, *, can_manage: bool, reading: ClinicalReading | None = None
) -> AnalysisOut:
    blinded = not can_manage and reading is None
    return AnalysisOut(
        id=analysis.id,
        image_id=analysis.image_id,
        status=analysis.status,
        attempts=analysis.attempts,
        roi=analysis.roi,
        model_version_id=analysis.model_version_id,
        probability_raw=None if blinded else analysis.probability_raw,
        probability=None if blinded else analysis.probability,
        member_spread=None if blinded else analysis.member_spread,
        decision=None if blinded else analysis.decision,
        shift_score=None if blinded else analysis.shift_score,
        shift_flag=None if blinded else analysis.shift_flag,
        warnings=[] if blinded else analysis.warnings,
        has_cam=not blinded and analysis.cam_key is not None,
        error=None if blinded else analysis.error,
        created_at=analysis.created_at,
        finished_at=analysis.finished_at,
        reading=reading,
        blinded_for_reader=blinded,
    )


def _image_out(image: Image, *, can_manage: bool, readings: dict[int, ClinicalReading]) -> ImageOut:
    return ImageOut(
        id=image.id,
        case_id=image.case_id,
        width=image.width,
        height=image.height,
        source_format=image.source_format,
        qc_flags=image.qc_flags,
        duplicate_of_id=image.duplicate_of_id,
        created_at=image.created_at,
        analyses=[
            _analysis_out(a, can_manage=can_manage, reading=readings.get(a.id))
            for a in image.analyses
        ],
    )


def _case_out(
    case: Case, user: User, readings: dict[int, ClinicalReading] | None = None
) -> CaseOut:
    can_manage = manages_case(case, user)
    images = [
        _image_out(image, can_manage=can_manage, readings=readings or {}) for image in case.images
    ]
    if not can_manage:
        for image in images:
            if any(flag.endswith("_other_case") for flag in image.qc_flags):
                image.duplicate_of_id = None
    return CaseOut(
        can_manage=can_manage,
        id=case.id,
        patient_ref=case.patient_ref,
        notes=case.notes,
        created_at=case.created_at,
        images=images,
    )


# ---------------------------------------------------------------- casos
@router.get("/cases", response_model=list[CaseSummary])
def list_cases(db: Session = Depends(get_db), user: User = Depends(_clinical)) -> list[CaseSummary]:
    query = (
        select(Case, func.count(Image.id))
        .outerjoin(Image, Image.case_id == Case.id)
        .group_by(Case.id)
        .order_by(Case.id.desc())
    )
    return [
        CaseSummary(
            id=case.id,
            patient_ref=case.patient_ref,
            notes=case.notes,
            created_at=case.created_at,
            image_count=count,
        )
        for case, count in db.execute(visible_cases(query, user))
    ]


@router.post("/cases", response_model=CaseOut, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreate, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> CaseOut:
    case = Case(patient_ref=body.patient_ref.strip(), notes=body.notes, created_by_id=user.id)
    db.add(case)
    db.flush()
    record(db, user, "case_created", "case", case.id)
    db.commit()
    return _case_out(case, user)


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int, response: Response, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> CaseOut:
    case = _case_or_404(db, case_id, user)
    response.headers["Cache-Control"] = "no-store"
    readings = db.scalars(
        select(ClinicalReading)
        .join(Analysis, Analysis.id == ClinicalReading.analysis_id)
        .join(Image, Image.id == Analysis.image_id)
        .where(Image.case_id == case.id, ClinicalReading.reader_id == user.id)
    )
    return _case_out(case, user, {reading.analysis_id: reading for reading in readings})


@router.get("/cases/{case_id}/readers", response_model=CaseReadersOut)
def list_case_readers(
    case_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> CaseReadersOut:
    case = _case_or_404(db, case_id, user, manage=True)
    assigned = CaseReader.reader_id.is_not(None)
    rows = db.execute(
        select(User.id, User.full_name, assigned)
        .outerjoin(CaseReader, (CaseReader.case_id == case_id) & (CaseReader.reader_id == User.id))
        .where(
            User.id != case.created_by_id,
            assigned | ((User.role == Role.medico) & User.is_active.is_(True)),
        )
        .order_by(User.full_name, User.id)
    )
    result = CaseReadersOut(assigned=[], eligible=[])
    for reader_id, name, is_assigned in rows:
        (result.assigned if is_assigned else result.eligible).append(
            ReaderIdentity(id=reader_id, full_name=name)
        )
    return result


@router.post("/cases/{case_id}/readers", response_model=CaseReaderOut, status_code=201)
def assign_case_reader(
    case_id: int,
    body: CaseReaderInput,
    db: Session = Depends(get_db),
    user: User = Depends(_clinical),
) -> CaseReader:
    case = _case_or_404(db, case_id, user, manage=True)
    reader = db.get(User, body.reader_id)
    if (
        reader is None
        or not reader.is_active
        or reader.role != Role.medico
        or reader.id == case.created_by_id
    ):
        raise HTTPException(422, "Seleccione un médico activo distinto del dueño del caso.")
    assignment = CaseReader(case_id=case_id, reader_id=reader.id, assigned_by=user.id)
    db.add(assignment)
    record(db, user, "case_reader_assigned", "case", case_id, reader_id=reader.id)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if db.get(CaseReader, (case_id, body.reader_id)) is not None:
            raise HTTPException(409, "El médico ya está asignado al caso.") from exc
        raise
    return assignment


@router.get("/worklist", response_model=list[WorklistItem])
def worklist(
    db: Session = Depends(get_db), user: User = Depends(require_roles(Role.medico))
) -> list[WorklistItem]:
    query = (
        select(
            Analysis.id.label("analysis_id"),
            Image.id.label("image_id"),
            Case.id.label("case_id"),
            Case.patient_ref,
            Analysis.finished_at,
        )
        .select_from(Analysis)
        .join(Image)
        .join(Case)
        .where(Analysis.status == AnalysisStatus.done, ~has_read_analysis(user))
        .order_by(func.coalesce(Analysis.finished_at, Analysis.created_at), Analysis.id)
    )
    return [WorklistItem.model_validate(row) for row in db.execute(visible_cases(query, user))]


# ---------------------------------------------------------------- imágenes
@router.post(
    "/cases/{case_id}/images", response_model=ImageOut, status_code=status.HTTP_201_CREATED
)
async def upload_image(
    case_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(_clinical),
) -> ImageOut:
    case = _case_or_404(db, case_id, user, manage=True)
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"El archivo supera {get_settings().max_upload_mb} MB.",
        )
    try:
        prepared = prepare_image(data, file.filename or "")
    except ImageDecodeError as exc:
        raise HTTPException(422, str(exc)) from exc
    image = store_image(db, case, prepared, DuplicateFinder(db, user.id))
    record(db, user, "image_uploaded", "image", image.id, source_format=image.source_format)
    db.commit()
    return _image_out(image, can_manage=True, readings={})


@router.get("/images/{image_id}/file")
def get_image_file(
    image_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> Response:
    image = _image_or_404(db, image_id, user)
    return Response(
        get_storage().get_bytes(image.storage_key), media_type="image/png", headers=_PNG_HEADERS
    )


# ---------------------------------------------------------------- análisis
@router.post(
    "/images/{image_id}/analyses", response_model=AnalysisOut, status_code=status.HTTP_202_ACCEPTED
)
def request_analysis(
    image_id: int,
    body: AnalysisCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(_clinical),
) -> AnalysisOut:
    image = _image_or_404(db, image_id, user, manage=True)
    model = get_active(db)
    if model is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "No hay un modelo activo. Un administrador debe registrar y activar uno.",
        )
    roi = body.roi.model_dump() if body.roi else None
    try:
        resolve_roi(roi, image.width, image.height, margin=0.0)
    except RoiError as exc:
        raise HTTPException(422, str(exc)) from exc

    analysis = Analysis(
        image_id=image.id, requested_by_id=user.id, model_version_id=model.id, roi=roi
    )
    db.add(analysis)
    db.flush()
    record(db, user, "analysis_requested", "analysis", analysis.id, model_version_id=model.id)
    db.commit()
    if get_settings().inline_worker:
        background.add_task(run_inline, analysis.id)
    return _analysis_out(analysis, can_manage=True)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(_clinical),
) -> AnalysisOut:
    analysis = _analysis_or_404(db, analysis_id, user)
    response.headers["Cache-Control"] = "no-store"
    return _analysis_out(
        analysis,
        can_manage=manages_case(analysis.image.case, user),
        reading=_own_reading(db, analysis.id, user.id),
    )


def _own_reading(db: Session, analysis_id: int, user_id: int) -> ClinicalReading | None:
    return db.scalar(
        select(ClinicalReading).where(
            ClinicalReading.analysis_id == analysis_id, ClinicalReading.reader_id == user_id
        )
    )


def _require_analysis_result(db: Session, analysis: Analysis, user: User) -> ClinicalReading | None:
    reading = _own_reading(db, analysis.id, user.id)
    if not manages_case(analysis.image.case, user) and reading is None:
        raise HTTPException(
            403, "Registre su lectura antes de consultar el resultado del análisis."
        )
    return reading


@router.post(
    "/analyses/{analysis_id}/reading",
    response_model=ClinicalReadingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reading(
    analysis_id: int,
    body: ClinicalReadingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_clinical),
) -> ClinicalReading:
    analysis = _analysis_or_404(db, analysis_id, user)
    if user.role == Role.investigador:
        raise HTTPException(403, "Su rol no permite registrar lecturas clínicas.")
    reader_id = user.id
    reading = ClinicalReading(
        analysis_id=analysis_id,
        reader_id=reader_id,
        birads=body.birads,
        notes=body.notes,
        blinded=not manages_case(analysis.image.case, user) or body.blinded,
    )
    db.add(reading)
    try:
        record(db, user, "clinical_reading_created", "analysis", analysis_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _own_reading(db, analysis_id, reader_id) is not None:
            raise HTTPException(409, "Ya registró una lectura para este análisis.") from exc
        raise
    return reading


@router.get("/analyses/{analysis_id}/reading", response_model=ClinicalReadingOut)
def get_reading(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> ClinicalReading:
    _analysis_or_404(db, analysis_id, user)
    reading = _own_reading(db, analysis_id, user.id)
    if reading is None:
        raise HTTPException(404, "Lectura clínica no encontrada.")
    return reading


@router.get(
    "/analyses/{analysis_id}/fhir",
    response_class=Response,
    responses={200: {"content": {"application/fhir+json": {}}}},
)
def export_fhir(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> Response:
    analysis = _analysis_or_404(db, analysis_id, user)
    _require_analysis_result(db, analysis, user)
    if analysis.status != AnalysisStatus.done:
        raise HTTPException(409, "El análisis aún no tiene un resultado.")
    query = select(ClinicalReading).where(ClinicalReading.analysis_id == analysis_id)
    if user.role != Role.admin:
        query = query.where(ClinicalReading.reader_id == user.id)
    bundle = analysis_bundle(analysis, db.scalars(query.order_by(ClinicalReading.id)))
    record(db, user, "analysis_fhir_exported", "analysis", analysis_id)
    db.commit()
    return JSONResponse(
        bundle, media_type="application/fhir+json", headers={"Cache-Control": "no-store"}
    )


@router.get("/analyses/{analysis_id}/cam")
def get_analysis_cam(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> Response:
    analysis = _analysis_or_404(db, analysis_id, user)
    _require_analysis_result(db, analysis, user)
    if analysis.status != AnalysisStatus.done or analysis.cam_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El mapa de activación no está disponible.")
    return Response(
        get_storage().get_bytes(analysis.cam_key),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/images/{image_id}/roi")
def suggest_roi(image_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)):
    image = _image_or_404(db, image_id, user, manage=True)
    storage = get_storage()
    path = storage.path("roi/segmenter.onnx")
    if not path.is_file():
        raise HTTPException(503, "El localizador experimental no está instalado.")
    roi = propose(storage.get_bytes(image.storage_key), path)
    record(
        db,
        user,
        "roi_suggested",
        "image",
        image.id,
        roi=roi,
        localizer_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    db.commit()
    return {"roi": roi}


@router.get("/analyses/{analysis_id}/report")
def analysis_report(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
):
    a = _analysis_or_404(db, analysis_id, user)
    reading = _require_analysis_result(db, a, user)
    if a.status != AnalysisStatus.done:
        raise HTTPException(409, "El análisis aún no tiene un resultado.")
    model = a.model_version
    warnings = {
        "roi_not_expected": "El clasificador se entrenó con la imagen completa y recibió un recorte.",
        "roi_expected": "El modelo requiere un recorte de la lesión.",
        "out_of_domain": "La imagen supera el umbral de cambio de dominio.",
        "shift_not_monitored": "Sin referencia para vigilar el dominio.",
        "members_disagree": "Los miembros del ensamble discrepan.",
        "demo_model": "Modelo de demostración sin entrenamiento.",
        "low_resolution": "Resolución baja.",
        "low_contrast": "Contraste bajo.",
        "color_content": "Se detectó contenido de color.",
        "exact_duplicate": "Duplicado exacto.",
        "near_duplicate": "Posible duplicado.",
        "exact_duplicate_other_case": "Idéntica a una imagen de otro caso.",
        "near_duplicate_other_case": "Casi idéntica a una imagen de otro caso.",
    }
    region = "Imagen completa"
    if a.roi:
        region = "Origen ({x:.1f}, {y:.1f}) px · Ancho {w:.1f} px · Alto {h:.1f} px".format(**a.roi)
    clinical_sections = []
    if reading is not None:
        comparison = "No evaluable para esta decisión del modelo."
        if a.decision in ("probably_benign", "suspicious"):
            clinical_suspicion = reading.birads not in ("1", "2", "3")
            agrees = clinical_suspicion == (a.decision == "suspicious")
            comparison = "Coincide" if agrees else "Discrepa"
            comparison += " según el umbral BI-RADS 4A."
        mode = "Ciega" if reading.blinded else "No ciega"
        clinical_sections = [
            (
                "Lectura clínica",
                f"BI-RADS {reading.birads} · {mode} · {reading.created_at:%Y-%m-%d %H:%M} UTC",
            ),
            ("Concordancia con el modelo", comparison),
        ]
    return pdf(
        f"Informe de análisis {a.id}",
        [
            (
                "Caso e imagen",
                f"Caso {a.image.case_id} · Imagen {a.image_id} · {a.finished_at:%Y-%m-%d %H:%M} UTC",
            ),
            ("Modelo", f"{model.name} {model.version}"),
            ("SHA-256", model.bundle_sha256),
            ("Región analizada", region),
            ("Resultado", DECISION_LABELS.get(a.decision, a.decision)),
            ("Probabilidad calibrada de malignidad", f"{a.probability:.1%}"),
            *clinical_sections,
            (
                "Advertencias del análisis",
                " ".join(warnings.get(code, code) for code in a.warnings) or "Ninguna registrada",
            ),
            ("Limitaciones del modelo", " ".join(model.card["limitations"])),
        ],
    )
