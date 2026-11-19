# ml

Código que produce los modelos que consume el backend. El formato de salida está en
[docs/model-bundle.md](../docs/model-bundle.md).

## Entorno

```bash
cd ml
python -m venv .venv
.venv\Scripts\activate
pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
pip install onnx onnxruntime pillow numpy
```

## Exportar un ensamble del estudio

`export_paper_bundle` convierte las cinco semillas de una variante del protocolo v3 en un bundle.
Necesita la corrida completa del estudio (`results/publication_v3_5seed`) y los datos de BUSI con
los que se entrenó; ambos se abren solo para lectura.

```bash
python -m ecoaudit_ml.export_paper_bundle ^
    --run-dir D:/busgen-ojemb-code/results/publication_v3_5seed ^
    --data-root D:/busgen-ojemb-code ^
    --out ../backend/data/bundles/paper-resnet18-control

cd ../backend
python -m app.cli register-model data/bundles/paper-resnet18-control --activate
```

Por defecto exporta ResNet-18, variante `source_only_matched` (el control emparejado, imagen
completa). La temperatura es la del ensamble publicada en `analysis/calibration_parameters.csv`.
La referencia de cambio de dominio se calcula con las imágenes de entrenamiento de origen y el
umbral con las de validación de origen.

Solo cubre la familia de imagen completa. Las variantes con recorte (ROI) usaron las máscaras del
conjunto de datos; exportarlas queda para cuando exista el ROI automático.

## Experimento con regiones automáticas

El entrenamiento del localizador, el reajuste de las cabezas y la comparación pareada están documentados en [la guía experimental](../tesis/README.md). El clasificador activo sigue siendo el de imagen completa.
