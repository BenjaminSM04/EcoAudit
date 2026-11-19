"""Control de calidad de la imagen y huella perceptual para detectar duplicados.

El hallazgo que motiva este módulo: en BUSI, las imágenes duplicadas o casi duplicadas producen
fuga de datos e inflan las métricas. El sistema marca el duplicado en el momento de la carga.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

MIN_SIDE = 128
LOW_CONTRAST_STD = 8.0
NEAR_DUPLICATE_BITS = 4  # distancia de Hamming máxima (de 64) para "casi duplicado"


def _gray(pixels: np.ndarray) -> np.ndarray:
    if pixels.ndim == 2:
        return pixels
    return np.asarray(Image.fromarray(pixels).convert("L"))


def dhash(pixels: np.ndarray) -> str:
    """Difference hash de 64 bits, en hexadecimal (16 caracteres)."""
    small = Image.fromarray(_gray(pixels)).resize((9, 8), Image.Resampling.LANCZOS)
    arr = np.asarray(small, dtype=np.int16)
    bits = (arr[:, 1:] > arr[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def hamming(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def quality_flags(pixels: np.ndarray) -> list[str]:
    flags: list[str] = []
    height, width = pixels.shape[:2]
    if min(height, width) < MIN_SIDE:
        flags.append("low_resolution")
    if float(_gray(pixels).std()) < LOW_CONTRAST_STD:
        flags.append("low_contrast")
    if pixels.ndim == 3:
        flags.append("color_content")  # Doppler o anotaciones en color: fuera del uso previsto
    return flags
