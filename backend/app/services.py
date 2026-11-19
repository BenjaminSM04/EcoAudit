"""Carga de imágenes: de-identificación, control de calidad y detección de duplicados.

La comparten la carga individual (``routers/cases.py``) y los lotes de cohorte
(``routers/cohorts.py``). Está separada en dos pasos para que un lote pueda validar todas sus
imágenes antes de escribir nada: ``prepare_image`` solo lee y calcula; ``store_image`` escribe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Case, Image
from .pipeline.imaging import decode_upload
from .pipeline.quality import NEAR_DUPLICATE_BITS, dhash, hamming, quality_flags
from .storage import get_storage

# La comparación perceptual entre casos mira solo las imágenes más recientes del usuario.
RECENT_IMAGES_LIMIT = 5000


@dataclass(frozen=True)
class PreparedImage:
    """Imagen ya decodificada y de-identificada. Sin los píxeles, para poder retener un lote
    entero en memoria."""

    png_bytes: bytes
    width: int
    height: int
    source_format: str
    pixel_sha256: str
    dhash: str
    qc_flags: list[str]


def prepare_image(data: bytes, filename: str = "") -> PreparedImage:
    """Decodifica y vuelve a codificar como PNG (se pierden EXIF y etiquetas DICOM) y calcula
    huellas y banderas de calidad. Lanza ``ImageDecodeError`` si no es una imagen admitida."""
    decoded = decode_upload(data, filename)
    return PreparedImage(
        png_bytes=decoded.png_bytes,
        width=decoded.width,
        height=decoded.height,
        source_format=decoded.source_format,
        pixel_sha256=decoded.pixel_sha256,
        dhash=dhash(decoded.pixels),
        qc_flags=quality_flags(decoded.pixels),
    )


@dataclass
class DuplicateFinder:
    """Busca la imagen de la que otra recién cargada es duplicado.

    Orden de prioridad: primero el mismo caso (exacto, si no, casi idéntico) y solo si no hay
    nada ahí, los otros casos del mismo dueño. Entre casos, el duplicado exacto se busca con el
    índice de ``pixel_sha256`` y el casi duplicado por distancia de Hamming sobre las
    ``RECENT_IMAGES_LIMIT`` imágenes más recientes del dueño. El dueño es quien sube: así el
    administrador compara contra sus propios casos.

    Un lote reutiliza el mismo objeto para todas sus imágenes: las huellas recientes se leen una
    sola vez y ``add`` incorpora cada imagen que se guarda.
    """

    db: Session
    owner_id: int
    _recent: list[tuple[int, int, int]] | None = field(default=None, init=False, repr=False)

    def _recent_fingerprints(self) -> list[tuple[int, int, int]]:
        if self._recent is None:
            rows = self.db.execute(
                select(Image.id, Image.case_id, Image.dhash)
                .join(Case, Case.id == Image.case_id)
                .where(Case.created_by_id == self.owner_id)
                .order_by(Image.id.desc())
                .limit(RECENT_IMAGES_LIMIT)
            )
            self._recent = [(i, case_id, int(h, 16)) for i, case_id, h in rows]
        return self._recent

    def find(self, case_id: int, pixel_sha256: str, fingerprint: str) -> tuple[str, int] | None:
        """Devuelve ``(bandera, id de la imagen original)`` o None si no hay duplicado."""
        near_in_case: int | None = None
        same_case = self.db.execute(
            select(Image.id, Image.pixel_sha256, Image.dhash)
            .where(Image.case_id == case_id)
            .order_by(Image.id)
        )
        for other_id, other_sha, other_hash in same_case:
            if other_sha == pixel_sha256:
                return "exact_duplicate", other_id
            if near_in_case is None and hamming(other_hash, fingerprint) <= NEAR_DUPLICATE_BITS:
                near_in_case = other_id
        if near_in_case is not None:
            return "near_duplicate", near_in_case

        exact = self.db.scalar(
            select(Image.id)
            .join(Case, Case.id == Image.case_id)
            .where(
                Case.created_by_id == self.owner_id,
                Image.case_id != case_id,
                Image.pixel_sha256 == pixel_sha256,
            )
            .order_by(Image.id)
            .limit(1)
        )
        if exact is not None:
            return "exact_duplicate_other_case", exact

        value = int(fingerprint, 16)
        best: tuple[int, int] | None = None  # (distancia, id); a igual distancia, la más antigua
        for other_id, other_case, other_hash in self._recent_fingerprints():
            if other_case == case_id:
                continue
            distance = (other_hash ^ value).bit_count()
            if distance <= NEAR_DUPLICATE_BITS and (best is None or (distance, other_id) < best):
                best = (distance, other_id)
        if best is not None:
            return "near_duplicate_other_case", best[1]
        return None

    def add(self, image: Image) -> None:
        """Registra una imagen recién guardada para las búsquedas siguientes."""
        if self._recent is not None:
            self._recent.insert(0, (image.id, image.case_id, int(image.dhash, 16)))
            del self._recent[RECENT_IMAGES_LIMIT:]


def store_image(
    db: Session, case: Case, prepared: PreparedImage, finder: DuplicateFinder
) -> Image:
    """Crea la fila de la imagen, marca duplicados y escribe el PNG en el almacén.

    No hace commit ni registra en la bitácora: eso lo decide quien llama. Si la escritura en el
    almacén falla, la excepción sube y quien llama debe revertir la transacción.
    """
    flags = list(prepared.qc_flags)
    duplicate = finder.find(case.id, prepared.pixel_sha256, prepared.dhash)
    duplicate_of: int | None = None
    if duplicate is not None:
        flag, duplicate_of = duplicate
        flags.append(flag)

    image = Image(
        case_id=case.id,
        storage_key="",
        pixel_sha256=prepared.pixel_sha256,
        dhash=prepared.dhash,
        width=prepared.width,
        height=prepared.height,
        source_format=prepared.source_format,
        qc_flags=flags,
        duplicate_of_id=duplicate_of,
    )
    db.add(image)
    db.flush()
    image.storage_key = f"images/{case.id}/{image.id}.png"
    storage = get_storage()
    try:
        storage.put_bytes(image.storage_key, prepared.png_bytes)
    except Exception:
        storage.delete(image.storage_key)  # no dejar un archivo a medias
        raise
    finder.add(image)
    return image
