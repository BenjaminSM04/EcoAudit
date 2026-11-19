"""Bundle de DEMOSTRACIÓN para pruebas automáticas y para recorrer la interfaz.

No es un modelo entrenado: una convolución con pesos aleatorios.
La ficha lleva ``"demo": true`` y el sistema lo advierte en cada resultado. Requiere el paquete
``onnx`` (dependencia de desarrollo).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .pipeline.bundle import CARD_FILE, SCHEMA_VERSION, ModelBundle


def _write_member(path: Path, rng: np.random.Generator, size: int, channels: int) -> tuple:
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    kernel = 8
    conv_w = rng.normal(0.0, 0.05, size=(channels, 3, kernel, kernel)).astype(np.float32)
    conv_b = rng.uniform(0.3, 0.8, size=(channels,)).astype(np.float32)  # > 0: nunca todo cero
    head_w = rng.uniform(0.2, 1.0, size=(1, channels)).astype(np.float32)
    head_b = np.asarray([-0.5], dtype=np.float32)

    nodes = [
        helper.make_node(
            "Conv", ["image", "conv_w", "conv_b"], ["conv"],
            kernel_shape=[kernel, kernel], strides=[kernel, kernel],
        ),
        helper.make_node("Relu", ["conv"], ["features"]),
        helper.make_node("GlobalAveragePool", ["features"], ["pooled"]),
        helper.make_node("Flatten", ["pooled"], ["embedding"], axis=1),
        helper.make_node("Gemm", ["embedding", "head_w", "head_b"], ["logit"], transB=1),
    ]
    grid = size // kernel
    graph = helper.make_graph(
        nodes,
        "ecoaudit_demo",
        [helper.make_tensor_value_info("image", TensorProto.FLOAT, ["n", 3, size, size])],
        [
            helper.make_tensor_value_info("logit", TensorProto.FLOAT, ["n", 1]),
            helper.make_tensor_value_info("features", TensorProto.FLOAT, ["n", channels, grid, grid]),
        ],
        initializer=[
            numpy_helper.from_array(conv_w, "conv_w"),
            numpy_helper.from_array(conv_b, "conv_b"),
            numpy_helper.from_array(head_w, "head_w"),
            numpy_helper.from_array(head_b, "head_b"),
        ],
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    onnx.save(model, str(path))
    return head_w[0], float(head_b[0])


def make_demo_bundle(
    out_dir: Path,
    *,
    size: int = 64,
    channels: int = 6,
    members: int = 3,
    seed: int = 0,
    temperature: float = 2.0,
    expects_roi: bool = False,
    with_shift: bool = True,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    member_entries = []
    for index in range(members):
        weight, bias = _write_member(out_dir / f"member_{index}.onnx", rng, size, channels)
        np.savez(out_dir / f"member_{index}_head.npz", weight=weight, bias=np.float32(bias))
        member_entries.append(
            {"onnx": f"member_{index}.onnx", "head": f"member_{index}_head.npz", "seed": index}
        )

    card = {
        "schema_version": SCHEMA_VERSION,
        "name": "demo-brillo",
        "version": f"0.0.{seed}",
        "demo": True,
        "architecture": "conv-demo",
        "task": "benign_vs_malignant",
        "input": {
            "size": size,
            "mean": [0.485, 0.456, 0.406],
            "std": [0.229, 0.224, 0.225],
            "expects_roi": expects_roi,
            "roi_margin": 0.1,
        },
        "members": member_entries,
        "calibration": {"temperature": temperature, "source": "valor arbitrario de demostración"},
        "decision": {"abstain_low": 0.35, "abstain_high": 0.65},
        "shift": None,
        "training_data": "Ninguno: pesos aleatorios.",
        "metrics": {},
        "limitations": [
            "Modelo de demostración sin entrenamiento. Sus resultados no tienen ningún significado."
        ],
    }
    (out_dir / CARD_FILE).write_text(json.dumps(card, indent=2, ensure_ascii=False), "utf-8")

    if with_shift:
        # Referencia "de entrenamiento": imágenes de ruido de 256 px (el worker las reduce a `size`). Lo que se aleje de ellas
        # (por ejemplo una imagen lisa) queda marcado como fuera de dominio.
        bundle = ModelBundle(out_dir)
        embeddings = np.stack(
            [
                bundle.predict(
                    np.clip(rng.normal(110, 45, size=(256, 256, 3)), 0, 255).astype(np.uint8)
                ).embeddings
                for _ in range(200)
            ],
            axis=1,
        )  # (M, 200, C)
        unit = embeddings / np.linalg.norm(embeddings, axis=-1, keepdims=True)
        reference, held_out = unit[:, :150], unit[:, 150:]
        np.savez(out_dir / "shift_reference.npz", embeddings=reference.astype(np.float32))
        k = 5
        distances = 1.0 - np.einsum("mnc,mhc->mhn", reference, held_out)
        nearest = np.sort(distances, axis=2)[:, :, k - 1]
        card["shift"] = {
            "reference": "shift_reference.npz",
            "method": "knn_cosine",
            "k": k,
            "threshold": float(nearest.mean(axis=0).max() * 3.0),
            "description": "Distancia coseno al 5.º vecino; umbral = 3 × máximo de 50 imágenes apartadas.",
        }
        (out_dir / CARD_FILE).write_text(json.dumps(card, indent=2, ensure_ascii=False), "utf-8")
    return out_dir
