# Contrato del bundle de modelo

Un bundle es un directorio que `ml/` exporta y el backend registra con
`python -m app.cli register-model RUTA [--activate]`. Al registrarlo se valida, se calcula su
SHA-256 y se copia al almacén; a partir de ahí es inmutable.

## Archivos

| Archivo | Contenido |
|---|---|
| `model_card.json` | Ficha del modelo (abajo) |
| `<miembro>.onnx` | Un archivo por miembro del ensamble |
| `<miembro>_head.npz` | Capa lineal final: `weight` (C,), `bias` () |
| `shift_reference.npz` | Opcional. `embeddings` (M, N, C): embeddings de las N imágenes de entrenamiento, por miembro |

## ONNX

- Entrada `image`: `float32` (N, 3, S, S), RGB normalizado con `input.mean` y `input.std`.
- Salida `logit`: (N, 1), logit de malignidad (maligno − benigno).
- Salida `features`: (N, C, h, w), el último mapa convolucional.

La arquitectura debe terminar en *global average pooling + capa lineal*, de modo que
`logit = weight · GAP(features) + bias`. El registro lo comprueba (`ModelBundle.self_check`) y
rechaza el bundle si no se cumple, porque de esa identidad depende que el mapa de activación
`ReLU(Σ_c weight_c · features_c)` sea fiel al modelo (equivale a Grad-CAM para estas redes).

## Preprocesamiento

El worker estira el recorte a S×S con interpolación bilineal de Pillow, divide entre 255 y
normaliza. Quien exporte debe calcular la referencia de cambio de dominio con ese mismo
preprocesamiento.

## `model_card.json`

```jsonc
{
  "schema_version": 1,
  "name": "paper-v3-resnet18-source-only-matched",
  "version": "1.0.0",
  "demo": false,                      // true: la interfaz advierte que no tiene validez
  "architecture": "resnet18",
  "input": {
    "size": 224,
    "mean": [0.485, 0.456, 0.406],
    "std": [0.229, 0.224, 0.225],
    "expects_roi": false,             // ¿se entrenó con recortes de la lesión?
    "roi_margin": 0.1                 // margen que se añade al ROI, como fracción de su tamaño
  },
  "members": [{ "onnx": "member_seed17.onnx", "head": "member_seed17_head.npz", "seed": 17 }],
  "calibration": { "temperature": 0.755, "source": "cómo y con qué datos se ajustó" },
  "decision": { "abstain_low": 0.35, "abstain_high": 0.65 },
  "shift": { "reference": "shift_reference.npz", "method": "knn_cosine", "k": 5,
             "threshold": 0.2, "description": "…" },
  "training_data": "texto obligatorio",
  "metrics": {},
  "limitations": ["lista obligatoria"]
}
```

`shift` puede ser `null`; entonces cada resultado lleva el aviso de que el cambio de dominio no
se monitorea.

## Reglas de decisión

1. Logit del ensamble = promedio de los logits de los miembros.
2. Probabilidad = `sigmoid(logit / temperature)`.
3. Puntaje de dominio = distancia coseno del embedding a su k-ésimo vecino más cercano entre las
   imágenes de entrenamiento, promediada entre miembros (0 = igual a una imagen conocida).
4. Si el puntaje supera `shift.threshold` → `out_of_domain`. Si no: `p ≥ abstain_high` →
   `suspicious`; `p ≤ abstain_low` → `probably_benign`; en medio → `indeterminate`.
