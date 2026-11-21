"""Casos, imágenes y análisis. Médicos e investigadores solo ven sus propios casos; el
administrador, todos."""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import record, require_roles
from ..fhir import analysis_bundle
from ..models import Analysis, AnalysisStatus, Case, ClinicalReading, Image, Role, User
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
    CaseSummary,
    ClinicalReadingCreate,
    ClinicalReadingOut,
    ImageOut,
)
from ..services import DuplicateFinder, prepare_image, store_image
from ..storage import get_storage
from ..worker import run_inline

router = APIRouter(prefix="/api", tags=["cases"])
_clinical = require_roles(Role.medico, Role.investigador, Role.admin)
_reader = require_roles(Role.medico, Role.admin)
_PNG_HEADERS = {"Cache-Control": "private, max-age=3600"}


# ---------------------------------------------------------------- acceso
def _case_or_404(db: Session, case_id: int, user: User) -> Case:
    case = db.get(Case, case_id)
    # 404 y no 403: no se revela la existencia de casos ajenos.
    if case is None or (user.role != Role.admin and case.created_by_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado.")
    return case


def _image_or_404(db: Session, image_id: int, user: User) -> Image:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imagen no encontrada.")
    _case_or_404(db, image.case_id, user)
    return image


def _analysis_or_404(db: Session, analysis_id: int, user: User) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Análisis no encontrado.")
    _image_or_404(db, analysis.image_id, user)
    return analysis


# ---------------------------------------------------------------- salida
def _analysis_out(analysis: Analysis, reading: ClinicalReading | None = None) -> AnalysisOut:
    return AnalysisOut.model_validate(
        {
            **{c.name: getattr(analysis, c.name) for c in Analysis.__table__.columns},
            "has_cam": analysis.cam_key is not None,
            "reading": reading,
        }
    )


def _image_out(image: Image, readings: dict[int, ClinicalReading] | None = None) -> ImageOut:
    return ImageOut(
        id=image.id,
        case_id=image.case_id,
        width=image.width,
        height=image.height,
        source_format=image.source_format,
        qc_flags=image.qc_flags,
        duplicate_of_id=image.duplicate_of_id,
        created_at=image.created_at,
        analyses=[_analysis_out(a, (readings or {}).get(a.id)) for a in image.analyses],
    )


def _case_out(case: Case, readings: dict[int, ClinicalReading] | None = None) -> CaseOut:
    return CaseOut(
        id=case.id,
        patient_ref=case.patient_ref,
        notes=case.notes,
        created_at=case.created_at,
        images=[_image_out(i, readings) for i in case.images],
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
    if user.role != Role.admin:
        query = query.where(Case.created_by_id == user.id)
    return [
        CaseSummary(
            id=case.id,
            patient_ref=case.patient_ref,
            notes=case.notes,
            created_at=case.created_at,
            image_count=count,
        )
        for case, count in db.execute(query)
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
    return _case_out(case)


@router.get("/cases/{case_id}", response_model=CaseOut)
def get_case(
    case_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> CaseOut:
    case = _case_or_404(db, case_id, user)
    readings = db.scalars(
        select(ClinicalReading)
        .join(Analysis, Analysis.id == ClinicalReading.analysis_id)
        .join(Image, Image.id == Analysis.image_id)
        .where(Image.case_id == case.id, ClinicalReading.reader_id == user.id)
    )
    return _case_out(case, {reading.analysis_id: reading for reading in readings})


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
    case = _case_or_404(db, case_id, user)
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
    return _image_out(image)


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
    image = _image_or_404(db, image_id, user)
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
    return _analysis_out(analysis)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)
) -> AnalysisOut:
    analysis = _analysis_or_404(db, analysis_id, user)
    return _analysis_out(analysis, _own_reading(db, analysis.id, user.id))


def _own_reading(db: Session, analysis_id: int, user_id: int) -> ClinicalReading | None:
    return db.scalar(
        select(ClinicalReading).where(
            ClinicalReading.analysis_id == analysis_id, ClinicalReading.reader_id == user_id
        )
    )


@router.post(
    "/analyses/{analysis_id}/reading",
    response_model=ClinicalReadingOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reading(
    analysis_id: int,
    body: ClinicalReadingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(_reader),
) -> ClinicalReading:
    _analysis_or_404(db, analysis_id, user)
    reader_id = user.id
    reading = ClinicalReading(analysis_id=analysis_id, reader_id=reader_id, **body.model_dump())
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
    if analysis.status != AnalysisStatus.done or analysis.cam_key is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El mapa de activación no está disponible.")
    return Response(
        get_storage().get_bytes(analysis.cam_key), media_type="image/png", headers=_PNG_HEADERS
    )


@router.post("/images/{image_id}/roi")
def suggest_roi(image_id: int, db: Session = Depends(get_db), user: User = Depends(_clinical)):
    image = _image_or_404(db, image_id, user)
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
            (
                "Advertencias del análisis",
                " ".join(warnings.get(code, code) for code in a.warnings) or "Ninguna registrada",
            ),
            ("Limitaciones del modelo", " ".join(model.card["limitations"])),
        ],
    )
