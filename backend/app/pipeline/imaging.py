"""Ingesta de imágenes con de-identificación por construcción.

De cualquier archivo subido solo se conservan los píxeles: se decodifica y se vuelve a codificar
como PNG, con lo que se descartan EXIF y todas las etiquetas DICOM (nombre, fecha de nacimiento,
institución, etc.).

Limitación conocida: el texto *quemado* dentro de la imagen (anotaciones del ecógrafo) no se
elimina. El usuario debe recortarlo antes de subir o delimitar la lesión con el ROI.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

import numpy as np
from PIL import Image, UnidentifiedImageError

MAX_PIXELS = 40_000_000


class ImageDecodeError(ValueError):
    """El archivo no es una imagen admitida. El mensaje se muestra al usuario."""


@dataclass(frozen=True)
class DecodedImage:
    png_bytes: bytes
    width: int
    height: int
    source_format: str
    pixel_sha256: str
    pixels: np.ndarray  # uint8, (H, W) o (H, W, 3)


def _is_dicom(data: bytes, filename: str) -> bool:
    return data[128:132] == b"DICM" or filename.lower().endswith((".dcm", ".dicom"))


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    if arr.dtype == np.uint8:
        return arr
    arr = arr.astype(np.float64)
    lo, hi = float(arr.min()), float(arr.max())
    if hi <= lo:
        return np.zeros(arr.shape, dtype=np.uint8)
    return np.round((arr - lo) / (hi - lo) * 255.0).astype(np.uint8)


def _decode_dicom(data: bytes) -> np.ndarray:
    import pydicom

    try:
        ds = pydicom.dcmread(io.BytesIO(data), force=True)
        arr = ds.pixel_array
    except Exception as exc:  # pydicom lanza tipos muy variados según el fallo
        raise ImageDecodeError(
            "No se pudo leer el DICOM. Si está comprimido (JPEG 2000/JPEG-LS), "
            "expórtelo sin compresión o como PNG."
        ) from exc

    samples = int(getattr(ds, "SamplesPerPixel", 1))
    photometric = str(getattr(ds, "PhotometricInterpretation", "MONOCHROME2"))
    # Multi-frame (cine loop): se toma el primer cuadro.
    if (samples == 1 and arr.ndim == 3) or (samples > 1 and arr.ndim == 4):
        arr = arr[0]
    if photometric.startswith("YBR"):
        from pydicom.pixels import convert_color_space

        arr = convert_color_space(arr, photometric, "RGB")
    arr = _to_uint8(arr)
    if photometric == "MONOCHROME1":
        arr = 255 - arr
    return arr


def _decode_raster(data: bytes) -> tuple[np.ndarray, str]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = (img.format or "unknown").lower()
            if img.width * img.height > MAX_PIXELS:
                raise ImageDecodeError("La imagen es demasiado grande.")
            img.seek(0)
            arr = np.asarray(img.convert("RGB"))
    except ImageDecodeError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageDecodeError("El archivo no es una imagen PNG, JPEG, BMP, TIFF o DICOM.") from exc
    return arr, fmt


def decode_upload(data: bytes, filename: str = "") -> DecodedImage:
    if _is_dicom(data, filename):
        arr, fmt = _decode_dicom(data), "dicom"
    else:
        arr, fmt = _decode_raster(data)

    if arr.ndim == 3 and arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.ndim == 3 and arr.shape[2] == 1:
        arr = arr[:, :, 0]
    if arr.ndim not in (2, 3) or (arr.ndim == 3 and arr.shape[2] != 3):
        raise ImageDecodeError("Formato de píxeles no admitido.")
    if arr.shape[0] * arr.shape[1] > MAX_PIXELS:
        raise ImageDecodeError("La imagen es demasiado grande.")
    # La ecografía en modo B es monocroma: si los tres canales coinciden se guarda un solo canal.
    if (
        arr.ndim == 3
        and np.array_equal(arr[..., 0], arr[..., 1])
        and np.array_equal(arr[..., 1], arr[..., 2])
    ):
        arr = arr[..., 0]
    arr = np.ascontiguousarray(arr)

    buffer = io.BytesIO()
    Image.fromarray(arr).save(buffer, format="PNG")
    digest = hashlib.sha256(f"{arr.shape}".encode() + arr.tobytes()).hexdigest()
    return DecodedImage(
        png_bytes=buffer.getvalue(),
        width=int(arr.shape[1]),
        height=int(arr.shape[0]),
        source_format=fmt,
        pixel_sha256=digest,
        pixels=arr,
    )


def load_png(data: bytes) -> np.ndarray:
    """Lee un PNG del almacén como RGB uint8 (H, W, 3)."""
    with Image.open(io.BytesIO(data)) as img:
        return np.asarray(img.convert("RGB"))
