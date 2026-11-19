"""Exporta un ensamble del estudio BUSI→BUS-BRA (protocolo v3) como bundle de EcoAudit.

El directorio de la corrida se abre solo para lectura. Ejemplo:

    python -m ecoaudit_ml.export_paper_bundle ^
        --run-dir D:/busgen-ojemb-code/results/publication_v3_5seed ^
        --data-root D:/busgen-ojemb-code ^
        --out ../backend/data/bundles/paper-resnet18-control

Qué hace:
1. Reconstruye cada red (backbone de torchvision + cabeza lineal de 2 clases) y carga sus pesos.
2. La exporta a ONNX con dos salidas: ``logit`` (maligno − benigno) y ``features``.
3. Comprueba que ONNX y PyTorch coinciden.
4. Guarda como referencia de cambio de dominio los embeddings de las imágenes de entrenamiento
   de origen y fija el umbral con las de validación de origen (percentil 99), que no están en la
   referencia. El puntaje es la distancia coseno al k-ésimo vecino más cercano.
5. Escribe ``model_card.json`` con la procedencia, las métricas publicadas y las limitaciones.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from PIL import Image
from torch import nn
from torchvision import models

SEEDS = (17, 42, 73, 101, 202)
SIZE = 224
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
SHIFT_K = 5


# ------------------------------------------------------------------ red
class PaperClassifier(nn.Module):
    """Misma estructura y nombres de parámetros que ``BreastClassifier`` del estudio."""

    def __init__(self, arch: str):
        super().__init__()
        if arch == "resnet18":
            self.backbone = models.resnet18(weights=None)
            feat_dim = self.backbone.fc.in_features
            self.backbone.fc = nn.Identity()
        elif arch == "efficientnet_b0":
            self.backbone = models.efficientnet_b0(weights=None)
            feat_dim = self.backbone.classifier[1].in_features
            self.backbone.classifier = nn.Identity()
        else:
            raise ValueError(f"Arquitectura no admitida: {arch}")
        self.arch = arch
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(feat_dim, 2))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.backbone(x))

    def feature_map(self, x: torch.Tensor) -> torch.Tensor:
        b = self.backbone
        if self.arch == "resnet18":
            x = b.maxpool(b.relu(b.bn1(b.conv1(x))))
            return b.layer4(b.layer3(b.layer2(b.layer1(x))))
        return b.features(x)


class Exportable(nn.Module):
    """Devuelve (logit de malignidad, último mapa convolucional)."""

    def __init__(self, model: PaperClassifier):
        super().__init__()
        self.model = model

    def forward(self, image: torch.Tensor):
        features = self.model.feature_map(image)
        logits = self.model.head[1](features.mean(dim=(2, 3)))
        return logits[:, 1:2] - logits[:, 0:1], features


# ------------------------------------------------------------------ utilidades
def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preprocess(path: Path) -> np.ndarray:
    """Debe coincidir con ``ModelBundle.preprocess`` del backend."""
    with Image.open(path) as img:
        resized = img.convert("RGB").resize((SIZE, SIZE), Image.Resampling.BILINEAR)
    tensor = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1) / 255.0
    mean = np.asarray(MEAN, dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(STD, dtype=np.float32).reshape(3, 1, 1)
    return ((tensor - mean) / std)[None].astype(np.float32)


def manifest_paths(manifest: Path, data_root: Path) -> list[Path]:
    with manifest.open(encoding="utf-8", newline="") as handle:
        paths = [data_root / row["image_path"] for row in csv.DictReader(handle)]
    missing = [p for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"{len(missing)} imágenes de {manifest.name} no existen, p. ej. {missing[0]}")
    return paths


def embeddings(session: ort.InferenceSession, paths: list[Path]) -> np.ndarray:
    rows = []
    for path in paths:
        (features,) = session.run(["features"], {"image": preprocess(path)})
        rows.append(features[0].mean(axis=(1, 2)))
    return np.asarray(rows, dtype=np.float64)


def unit(x: np.ndarray) -> np.ndarray:
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def knn_distance(x: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Distancia coseno de cada fila de ``x`` a su k-ésimo vecino en ``reference`` (unitarios)."""
    return np.sort(1.0 - x @ reference.T, axis=1)[:, SHIFT_K - 1]


def read_ensemble_row(run_dir: Path, arch: str, method: str) -> dict:
    with (run_dir / "analysis" / "calibration_parameters.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row["arch"], row["method"], row["variant"]) == (arch, method, "5_seed_logit_ensemble"):
                return row
    raise LookupError(f"Sin calibración de ensamble para {arch}/{method}.")


def read_metrics(run_dir: Path, arch: str, method: str) -> dict:
    wanted = {"auc_raw", "brier_calibrated", "ece_calibrated", "nll_calibrated"}
    out: dict = {}
    with (run_dir / "analysis" / "ensemble_metrics.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["arch"] == arch and row["method"] == method and row["metric"] in wanted:
                out[row["metric"]] = {
                    "estimate": round(float(row["estimate"]), 4),
                    "ci95": [round(float(row["ci_low"]), 4), round(float(row["ci_high"]), 4)],
                    "n_patients": int(row["n_test_patients"]),
                    "unit": row["unit"],
                }
    return out


# ------------------------------------------------------------------ principal
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True,
                        help="Raíz contra la que se resuelven las rutas de los manifiestos")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--arch", default="resnet18", choices=["resnet18", "efficientnet_b0"])
    parser.add_argument("--method", default="source_only_matched")
    parser.add_argument("--abstain-low", type=float, default=0.35)
    parser.add_argument("--abstain-high", type=float, default=0.65)
    args = parser.parse_args()

    run_dir: Path = args.run_dir
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    probe = torch.randn(2, 3, SIZE, SIZE)

    train_paths = manifest_paths(run_dir / "splits" / "source_train_manifest.csv", args.data_root)
    val_paths = manifest_paths(run_dir / "splits" / "source_val_manifest.csv", args.data_root)

    members, references, val_distances = [], [], []
    for seed in SEEDS:
        ckpt_path = run_dir / "checkpoints" / "v3" / f"main_{args.arch}_seed{seed}_{args.method}.pt"
        checkpoint = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        model = PaperClassifier(args.arch)
        model.load_state_dict(checkpoint["model_state"], strict=True)
        model.eval()
        exportable = Exportable(model).eval()

        onnx_name = f"member_seed{seed}.onnx"
        torch.onnx.export(
            exportable, probe, str(out / onnx_name),
            input_names=["image"], output_names=["logit", "features"],
            dynamic_axes={"image": {0: "n"}, "logit": {0: "n"}, "features": {0: "n"}},
            opset_version=17, dynamo=False,
        )
        session = ort.InferenceSession(str(out / onnx_name), providers=["CPUExecutionProvider"])
        onnx_logit, _ = session.run(["logit", "features"], {"image": probe.numpy()})
        with torch.no_grad():
            two_class = model(probe)
        torch_logit = (two_class[:, 1] - two_class[:, 0]).numpy()
        gap = float(np.abs(onnx_logit.reshape(-1) - torch_logit).max())
        if gap > 1e-3:
            raise RuntimeError(f"seed {seed}: ONNX y PyTorch difieren en {gap:.2e}")

        linear = model.head[1]
        head_name = f"member_seed{seed}_head.npz"
        np.savez(
            out / head_name,
            weight=(linear.weight[1] - linear.weight[0]).detach().numpy().astype(np.float32),
            bias=np.float32((linear.bias[1] - linear.bias[0]).item()),
        )

        reference = unit(embeddings(session, train_paths))
        references.append(reference)
        val_distances.append(knn_distance(unit(embeddings(session, val_paths)), reference))

        members.append({
            "onnx": onnx_name,
            "head": head_name,
            "seed": seed,
            "source_checkpoint": ckpt_path.name,
            "source_checkpoint_sha256": sha256_file(ckpt_path),
            "best_epoch": int(checkpoint["best_epoch"]),
        })
        print(f"seed {seed}: exportado (diferencia ONNX-PyTorch: {gap:.1e})")

    np.savez(out / "shift_reference.npz", embeddings=np.asarray(references, dtype=np.float32))
    ensemble_val = np.mean(val_distances, axis=0)  # misma regla que el worker: media entre miembros
    threshold = float(np.percentile(ensemble_val, 99))

    calibration = read_ensemble_row(run_dir, args.arch, args.method)
    card = {
        "schema_version": 1,
        "name": f"paper-v3-{args.arch}-{args.method}".replace("_", "-"),
        "version": "1.0.0",
        "demo": False,
        "architecture": args.arch,
        "task": "benign_vs_malignant",
        "input": {"size": SIZE, "mean": list(MEAN), "std": list(STD),
                  "expects_roi": False, "roi_margin": 0.1},
        "members": members,
        "calibration": {
            "temperature": float(calibration["temperature"]),
            "source": (
                f"temperature scaling del ensamble de 5 semillas, ajustado a nivel paciente en la "
                f"cohorte de calibración de BUS-BRA ({calibration['n_calibration_patients']} pacientes)"
            ),
        },
        "decision": {
            "abstain_low": args.abstain_low,
            "abstain_high": args.abstain_high,
            "note": "Zona de abstención provisional, sin validar.",
        },
        "shift": {
            "reference": "shift_reference.npz",
            "method": "knn_cosine",
            "k": SHIFT_K,
            "threshold": threshold,
            "description": (
                f"Distancia coseno al {SHIFT_K}.º vecino entre {len(train_paths)} imágenes de "
                f"entrenamiento de Curated BUSI; umbral: percentil 99 de {len(val_paths)} imágenes de "
                f"validación de origen"
            ),
        },
        "training_data": (
            "Curated BUSI (Egipto) tras la revisión de integridad del protocolo v3; continuación del "
            "entrenamiento solo con origen (control emparejado en actualizaciones)."
        ),
        "metrics": {
            "cohort": "BUS-BRA, cohorte de prueba histórica, nivel paciente (reanálisis bloqueado)",
            **read_metrics(run_dir, args.arch, args.method),
        },
        "limitations": [
            "Prototipo de investigación: no es un dispositivo médico ni fue validado clínicamente.",
            "Las métricas provienen de una cohorte de prueba histórica ya inspeccionada en trabajo "
            "exploratorio; no equivalen a una validación externa independiente.",
            "La temperatura se ajustó con probabilidades agregadas por paciente; el sistema la aplica "
            "por imagen.",
            "La zona de abstención y el umbral de cambio de dominio son provisionales.",
            "Entrenado con la imagen completa: analizar un recorte (ROI) lo saca de su uso previsto.",
        ],
    }
    (out / "model_card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False), "utf-8")
    print(f"Bundle escrito en {out}")
    print(f"Temperatura {card['calibration']['temperature']:.4f}; umbral de dominio {threshold:.3f} "
          f"(validación de origen: mediana {np.median(ensemble_val):.3f}, máx {ensemble_val.max():.3f})")


if __name__ == "__main__":
    main()
