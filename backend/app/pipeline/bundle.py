"""Paquete de modelo ("bundle"): el contrato entre ``ml/`` (que lo exporta) y el worker.

Un bundle es un directorio con:

* ``model_card.json``: ficha del modelo (ver ``docs/model-bundle.md``).
* un ONNX por miembro del ensamble, con entrada ``image`` (N,3,S,S) y dos salidas:
  ``logit`` (N,1), el logit de malignidad, y ``features`` (N,C,h,w), el último mapa convolucional.
* un ``.npz`` por miembro con la capa lineal final (``weight`` (C,), ``bias`` ()).
* opcionalmente ``shift_reference.npz`` con ``embeddings`` (M,N,C): los embeddings de las N
  imágenes de entrenamiento, por miembro.

Las arquitecturas admitidas terminan en *global average pooling + capa lineal*. Para ellas el mapa
de activación de clase (CAM) ``sum_c weight_c * features_c`` es exactamente Grad-CAM, así que la
explicación se calcula sin gradientes y basta ONNX Runtime en producción.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image

SCHEMA_VERSION = 1
CARD_FILE = "model_card.json"


class BundleError(ValueError):
    """El bundle no cumple el contrato."""


@dataclass(frozen=True)
class Prediction:
    logits: np.ndarray  # (M,) logit de malignidad por miembro
    embeddings: np.ndarray  # (M, C)
    cam: np.ndarray  # (h, w) en [0, 1], promedio del ensamble


def bundle_sha256(directory: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(p for p in Path(directory).rglob("*") if p.is_file()):
        digest.update(file.relative_to(directory).as_posix().encode())
        digest.update(b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def read_card(directory: Path) -> dict:
    card_path = Path(directory) / CARD_FILE
    if not card_path.is_file():
        raise BundleError(f"Falta {CARD_FILE}.")
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BundleError(f"{CARD_FILE} no es JSON válido: {exc}") from exc
    _validate_card(card)
    return card


def _validate_card(card: dict) -> None:
    def need(condition: bool, message: str) -> None:
        if not condition:
            raise BundleError(f"model_card.json: {message}")

    need(card.get("schema_version") == SCHEMA_VERSION, f"schema_version debe ser {SCHEMA_VERSION}")
    for key in ("name", "version", "architecture", "training_data"):
        need(isinstance(card.get(key), str) and card[key].strip() != "", f"falta '{key}'")
    need(isinstance(card.get("limitations"), list), "falta 'limitations' (lista)")

    inp = card.get("input") or {}
    need(isinstance(inp.get("size"), int) and inp["size"] > 0, "input.size inválido")
    for key in ("mean", "std"):
        need(
            isinstance(inp.get(key), list) and len(inp[key]) == 3,
            f"input.{key} debe tener 3 valores",
        )
    need(isinstance(inp.get("expects_roi"), bool), "falta input.expects_roi (bool)")

    members = card.get("members")
    need(isinstance(members, list) and len(members) >= 1, "se requiere al menos un miembro")
    for member in members:
        need("onnx" in member and "head" in member, "cada miembro necesita 'onnx' y 'head'")

    temperature = (card.get("calibration") or {}).get("temperature")
    need(isinstance(temperature, int | float) and temperature > 0, "calibration.temperature > 0")

    decision = card.get("decision") or {}
    low, high = decision.get("abstain_low"), decision.get("abstain_high")
    need(
        isinstance(low, int | float) and isinstance(high, int | float) and 0 <= low <= high <= 1,
        "decision.abstain_low/abstain_high deben cumplir 0 <= low <= high <= 1",
    )

    shift = card.get("shift")
    if shift is not None:
        need("reference" in shift, "shift.reference faltante")
        need(shift.get("method") == "knn_cosine", "shift.method debe ser 'knn_cosine'")
        need(isinstance(shift.get("k"), int) and shift["k"] >= 1, "shift.k debe ser un entero >= 1")
        need(isinstance(shift.get("threshold"), int | float), "shift.threshold faltante")


def _unit(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=-1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class ModelBundle:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.card = read_card(self.directory)
        inp = self.card["input"]
        self.size: int = inp["size"]
        self._mean = np.asarray(inp["mean"], dtype=np.float32).reshape(3, 1, 1)
        self._std = np.asarray(inp["std"], dtype=np.float32).reshape(3, 1, 1)

        options = ort.SessionOptions()
        options.log_severity_level = 3
        self._sessions: list[ort.InferenceSession] = []
        self._weights: list[np.ndarray] = []
        self._biases: list[float] = []
        for member in self.card["members"]:
            onnx_path = self.directory / member["onnx"]
            head_path = self.directory / member["head"]
            if not onnx_path.is_file() or not head_path.is_file():
                raise BundleError(f"Faltan archivos del miembro {member['onnx']!r}.")
            session = ort.InferenceSession(
                str(onnx_path), sess_options=options, providers=["CPUExecutionProvider"]
            )
            outputs = {o.name for o in session.get_outputs()}
            if session.get_inputs()[0].name != "image" or not {"logit", "features"} <= outputs:
                raise BundleError(
                    f"{member['onnx']}: se espera entrada 'image' y salidas 'logit' y 'features'."
                )
            with np.load(head_path) as head:
                self._weights.append(np.asarray(head["weight"], dtype=np.float32).reshape(-1))
                self._biases.append(float(head["bias"]))
            self._sessions.append(session)

        self._shift_reference: np.ndarray | None = None
        self._shift_k = 1
        shift = self.card.get("shift")
        if shift is not None:
            ref_path = self.directory / shift["reference"]
            if not ref_path.is_file():
                raise BundleError("Falta el archivo de referencia de cambio de dominio.")
            with np.load(ref_path) as ref:
                reference = np.asarray(ref["embeddings"], dtype=np.float64)
            self._shift_k = int(shift["k"])
            if reference.ndim != 3 or reference.shape[0] != len(self._sessions):
                raise BundleError("La referencia de cambio de dominio no coincide con el ensamble.")
            if reference.shape[1] < self._shift_k:
                raise BundleError("La referencia tiene menos imágenes que shift.k.")
            self._shift_reference = _unit(reference)

    # ------------------------------------------------------------------ inferencia
    def preprocess(self, rgb: np.ndarray) -> np.ndarray:
        """RGB uint8 (H,W,3) → tensor (1,3,S,S). Estira a S×S, igual que en el entrenamiento."""
        resized = Image.fromarray(rgb).resize((self.size, self.size), Image.Resampling.BILINEAR)
        tensor = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1) / 255.0
        return ((tensor - self._mean) / self._std)[None].astype(np.float32)

    def predict(self, rgb: np.ndarray) -> Prediction:
        tensor = self.preprocess(rgb)
        logits, embeddings, cams = [], [], []
        for session, weight in zip(self._sessions, self._weights, strict=True):
            logit, features = session.run(["logit", "features"], {"image": tensor})
            features = features[0]  # (C, h, w)
            logits.append(float(np.asarray(logit).reshape(-1)[0]))
            embeddings.append(features.mean(axis=(1, 2)))
            cam = np.maximum(np.tensordot(weight, features, axes=(0, 0)), 0.0)
            peak = float(cam.max())
            cams.append(cam / peak if peak > 0 else cam)
        cam = np.mean(cams, axis=0)
        peak = float(cam.max())
        return Prediction(
            logits=np.asarray(logits, dtype=np.float64),
            embeddings=np.asarray(embeddings, dtype=np.float64),
            cam=(cam / peak if peak > 0 else cam).astype(np.float32),
        )

    def shift_score(self, embeddings: np.ndarray) -> float | None:
        """Distancia coseno al k-ésimo vecino más cercano entre las imágenes de entrenamiento,
        promediada entre miembros. 0 = igual a una imagen conocida. None si no hay referencia.

        Se eligió tras medirlo: la distancia de Mahalanobis no distinguía ni ruido puro, porque
        hay menos imágenes de entrenamiento que dimensiones (ver ``docs/adr/0004``).
        """
        if self._shift_reference is None:
            return None
        if embeddings.shape[-1] != self._shift_reference.shape[-1]:
            raise BundleError("El embedding no tiene la dimensión de la referencia.")
        similarity = np.einsum("mnc,mc->mn", self._shift_reference, _unit(embeddings))
        distance = np.sort(1.0 - similarity, axis=1)[:, self._shift_k - 1]
        return float(distance.mean())

    # ------------------------------------------------------------------ verificación
    def self_check(self, tolerance: float = 1e-2) -> None:
        """Comprueba que ``logit == weight · GAP(features) + bias``; si no, el CAM sería falso."""
        rng = np.random.default_rng(0)
        rgb = rng.integers(0, 256, size=(self.size, self.size, 3), dtype=np.uint8)
        prediction = self.predict(rgb)
        for index, (weight, bias) in enumerate(zip(self._weights, self._biases, strict=True)):
            if weight.shape[0] != prediction.embeddings.shape[1]:
                raise BundleError(f"Miembro {index}: la cabeza no coincide con 'features'.")
            rebuilt = float(prediction.embeddings[index] @ weight + bias)
            if abs(rebuilt - prediction.logits[index]) > tolerance * max(1.0, abs(rebuilt)):
                raise BundleError(
                    f"Miembro {index}: el logit ({prediction.logits[index]:.4f}) no coincide con "
                    f"weight·GAP(features)+bias ({rebuilt:.4f})."
                )
