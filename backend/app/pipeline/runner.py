"""Orquestación de un análisis: ROI → ensamble → calibración → decisión → CAM."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .bundle import ModelBundle

# Si los miembros del ensamble discrepan más que esto (desv. estándar de la probabilidad
# calibrada), se advierte al usuario.
DISAGREEMENT_STD = 0.15


class RoiError(ValueError):
    """ROI fuera de la imagen o degenerado."""


@dataclass(frozen=True)
class AnalysisResult:
    probability_raw: float
    probability: float
    member_spread: float
    decision: str
    shift_score: float | None
    shift_flag: bool | None
    warnings: list[str] = field(default_factory=list)
    cam_overlay_png: bytes = b""


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


def resolve_roi(
    roi: dict | None, width: int, height: int, margin: float
) -> tuple[int, int, int, int]:
    """Devuelve (x0, y0, x1, y1) del recorte. Sin ROI, la imagen completa."""
    if roi is None:
        return 0, 0, width, height
    try:
        x, y, w, h = (float(roi[k]) for k in ("x", "y", "w", "h"))
    except (KeyError, TypeError, ValueError) as exc:
        raise RoiError("El ROI debe tener x, y, w, h numéricos.") from exc
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w < 8 or h < 8:
        raise RoiError("El ROI es demasiado pequeño.")
    if x < 0 or y < 0 or x + w > width or y + h > height:
        raise RoiError("El ROI queda fuera de la imagen.")
    x0 = max(0, math.floor(x - margin * w))
    y0 = max(0, math.floor(y - margin * h))
    x1 = min(width, math.ceil(x + w + margin * w))
    y1 = min(height, math.ceil(y + h + margin * h))
    return x0, y0, x1, y1


def render_cam_overlay(
    cam: np.ndarray, box: tuple[int, int, int, int], width: int, height: int
) -> bytes:
    """PNG RGBA del tamaño de la imagen: color cálido con opacidad proporcional al CAM."""
    x0, y0, x1, y1 = box
    heat = Image.fromarray(np.round(cam * 255).astype(np.uint8)).resize(
        (x1 - x0, y1 - y0), Image.Resampling.BICUBIC
    )
    value = np.asarray(heat, dtype=np.float32) / 255.0
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    region = rgba[y0:y1, x0:x1]
    region[..., 0] = 255
    region[..., 1] = np.round(255 * np.clip(1.6 * value - 0.6, 0, 1)).astype(np.uint8)
    region[..., 2] = 0
    region[..., 3] = np.round(200 * np.clip(value, 0, 1) ** 1.5).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG")
    return buffer.getvalue()


def analyze(rgb: np.ndarray, roi: dict | None, bundle: ModelBundle) -> AnalysisResult:
    card = bundle.card
    height, width = rgb.shape[:2]
    warnings: list[str] = []

    expects_roi = card["input"]["expects_roi"]
    margin = float(card["input"].get("roi_margin", 0.0))
    if expects_roi and roi is None:
        warnings.append("roi_expected")  # el modelo se entrenó con recortes de la lesión
    if not expects_roi and roi is not None:
        warnings.append("roi_not_expected")  # el modelo se entrenó con la imagen completa
    box = resolve_roi(roi, width, height, margin)
    crop = rgb[box[1] : box[3], box[0] : box[2]]

    prediction = bundle.predict(crop)
    temperature = float(card["calibration"]["temperature"])
    mean_logit = float(prediction.logits.mean())  # regla del protocolo v3: promedio de logits
    probability_raw = sigmoid(mean_logit)
    probability = sigmoid(mean_logit / temperature)
    spread = float(np.std([sigmoid(float(v) / temperature) for v in prediction.logits]))
    if spread > DISAGREEMENT_STD:
        warnings.append("members_disagree")

    shift_score = bundle.shift_score(prediction.embeddings)
    shift_flag: bool | None = None
    if shift_score is not None:
        shift_flag = shift_score > float(card["shift"]["threshold"])
    else:
        warnings.append("shift_not_monitored")

    low = float(card["decision"]["abstain_low"])
    high = float(card["decision"]["abstain_high"])
    if shift_flag:
        decision = "out_of_domain"
        warnings.append("out_of_domain")
    elif probability >= high:
        decision = "suspicious"
    elif probability <= low:
        decision = "probably_benign"
    else:
        decision = "indeterminate"

    if card.get("demo"):
        warnings.append("demo_model")

    return AnalysisResult(
        probability_raw=probability_raw,
        probability=probability,
        member_spread=spread,
        decision=decision,
        shift_score=shift_score,
        shift_flag=shift_flag,
        warnings=warnings,
        cam_overlay_png=render_cam_overlay(prediction.cam, box, width, height),
    )
