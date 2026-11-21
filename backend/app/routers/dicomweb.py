"""Recepción mínima de instancias DICOM por STOW-RS."""

import hmac
import io
import re
from email.message import Message

import pydicom
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..deps import record, require_roles
from ..models import Case, Role, User
from ..pipeline.imaging import ImageDecodeError
from ..services import DuplicateFinder, prepare_image, store_image
from ..storage import get_storage

router = APIRouter(prefix="/api/dicomweb", tags=["dicomweb"])
_uploader = require_roles(Role.medico, Role.admin)
_MAX_PARTS = 100


def _content_type(value: str) -> Message:
    header = Message()
    header["Content-Type"] = value
    return header


def _multipart(body: bytes, boundary: str) -> list[tuple[str, bytes]]:
    # Un delimitador solo cuenta al inicio de una línea, no dentro de los píxeles.
    delimiter = re.compile(
        rb"(?:\A|\r\n)--" + re.escape(boundary.encode("ascii")) + rb"(--)?[ \t]*(?:\r\n|\Z)"
    )
    parts = []
    previous = None
    for marker in delimiter.finditer(body):
        if previous is not None:
            if len(parts) >= _MAX_PARTS:
                raise HTTPException(413, f"El envío supera {_MAX_PARTS} instancias.")
            part = body[previous : marker.start()]
            headers, separator, payload = part.partition(b"\r\n\r\n")
            content_type = ""
            if separator and len(headers) <= 8192:
                for line in headers.split(b"\r\n"):
                    name, _, value = line.partition(b":")
                    if name.lower() == b"content-type":
                        content_type = _content_type(
                            value.decode("latin-1").strip()
                        ).get_content_type()
                        break
            parts.append((content_type, payload))
        if marker[1] is not None:
            if parts:
                return parts
            break
        previous = marker.end()
    raise HTTPException(400, "El cuerpo multipart/related está vacío o no tiene cierre válido.")


def _patient_ref(data: bytes, secret: bytes) -> str:
    try:
        dataset = pydicom.dcmread(
            io.BytesIO(data), force=True, stop_before_pixels=True, specific_tags=["PatientID"]
        )
        patient_id = dataset.get("PatientID")
    except Exception as exc:
        raise ImageDecodeError("No se pudo leer la instancia DICOM.") from exc
    if not isinstance(patient_id, str) or not patient_id.strip():
        raise ImageDecodeError("La instancia DICOM requiere PatientID.")
    return "PAC-" + hmac.digest(secret, patient_id.encode(), "sha256").hex()[:12]


def _store_instances(
    body: bytes, boundary: str | None, db: Session, user: User, limit: int
) -> JSONResponse:
    parts = _multipart(body, boundary) if boundary is not None else [("application/dicom", body)]
    secret = get_settings().secret_key.encode()
    prepared = []
    failures = []
    for index, (media_type, data) in enumerate(parts, 1):
        try:
            if media_type != "application/dicom":
                raise ImageDecodeError("La parte debe tener Content-Type application/dicom.")
            if len(data) > limit:
                raise ImageDecodeError("La instancia supera el límite de carga.")
            patient_ref = _patient_ref(data, secret)
            prepared.append((patient_ref, prepare_image(data, "instancia.dcm")))
        except ImageDecodeError as exc:
            failures.append({"indice": index, "motivo": str(exc)})

    saved = []
    if prepared:
        user_id = user.id
        storage = get_storage()
        written = []
        try:
            # Serializa las recepciones del mismo dueño en PostgreSQL y las escrituras en SQLite.
            db.execute(update(User).where(User.id == user_id).values(is_active=User.is_active))
            finder = DuplicateFinder(db, user_id)
            for patient_ref, data in prepared:
                case = db.scalar(
                    select(Case)
                    .where(Case.created_by_id == user_id, Case.patient_ref == patient_ref)
                    .order_by(Case.id)
                    .limit(1)
                )
                if case is None:
                    case = Case(created_by_id=user_id, patient_ref=patient_ref)
                    db.add(case)
                    db.flush()
                    record(db, user, "case_created", "case", case.id)
                image = store_image(db, case, data, finder)
                written.append(image.storage_key)
                record(
                    db, user, "image_uploaded", "image", image.id, source_format="dicom", via="stow"
                )
                saved.append(
                    {
                        "case_id": case.id,
                        "image_id": image.id,
                        "patient_ref": patient_ref,
                        "qc_flags": image.qc_flags,
                    }
                )
            db.commit()
        except Exception:
            for key in written:
                storage.delete(key)
            db.rollback()
            raise
    code = 200 if not failures else (202 if saved else 400)
    return JSONResponse({"instancias": saved, "fallos": failures}, status_code=code)


@router.post(
    "/studies",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}}
                for media in ("application/dicom", "multipart/related")
            },
        }
    },
)
async def store_studies(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(_uploader),
) -> JSONResponse:
    header = _content_type(request.headers.get("content-type", ""))
    media_type = header.get_content_type()
    boundary = None
    if media_type == "multipart/related":
        if str(header.get_param("type", "")).lower() != "application/dicom":
            raise HTTPException(415, "El tipo de las partes debe ser application/dicom.")
        boundary = header.get_boundary()
        if not boundary or not re.fullmatch(r"[A-Za-z0-9'()+_,./:=? -]{1,70}", boundary):
            raise HTTPException(400, "El separador multipart/related es inválido.")
    elif media_type != "application/dicom":
        raise HTTPException(415, "Se requiere application/dicom o multipart/related.")

    limit = get_settings().max_upload_mb * 1024 * 1024
    request_limit = limit if boundary is None else 4 * limit
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > request_limit:
            raise HTTPException(413, "El cuerpo supera el límite de carga.")
        body.extend(chunk)
    return await run_in_threadpool(_store_instances, bytes(body), boundary, db, user, limit)
