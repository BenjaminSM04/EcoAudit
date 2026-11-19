# ADR 0001: inferencia con ONNX Runtime y mapa de activación sin gradientes

**Estado:** aceptada.

## Contexto

Los modelos se entrenan con PyTorch. Servirlos con PyTorch obligaría a instalar un framework de
varios gigabytes en producción, y Grad-CAM necesita gradientes, que ONNX Runtime no ofrece.

## Decisión

Los modelos se exportan a ONNX con dos salidas: el logit y el último mapa convolucional. Solo se
admiten arquitecturas que terminan en *global average pooling + capa lineal* (ResNet,
EfficientNet). Para ellas, `Σ_c w_c · features_c` (CAM) coincide con Grad-CAM, así que la
explicación se calcula con una multiplicación y sin gradientes.

## Consecuencias

- La imagen de producción no incluye PyTorch.
- Al registrar un modelo se comprueba numéricamente que el logit se reconstruye a partir del mapa
  y de la capa lineal; si no, se rechaza.
- Quedan fuera las arquitecturas con otra cabeza (por ejemplo, transformers con token de clase).
  Admitirlas exigiría otro método de explicación.
- SHAP, que el estudio usó, no se ofrece en línea.
