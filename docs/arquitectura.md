# Arquitectura

## Del estudio al sistema

Cada decisión de diseño responde a un hallazgo del estudio BUSI→BUS-BRA (protocolo v3).

| Hallazgo | Requisito | Dónde vive |
|---|---|---|
| Ninguna de las seis comparaciones primarias de adaptación (DANN, CORAL, MMD) superó al control | El sistema no promete adaptarse solo: mide cuánto se aleja la imagen de los datos de entrenamiento y avisa | `pipeline/bundle.py` (`shift_score`), `pipeline/runner.py` |
| El recorte de la lesión mejoró el AUROC en una comparación secundaria | El usuario puede trazar un ROI; la ficha del modelo declara si espera recorte o imagen completa | `ImageWorkspace.tsx`, `pipeline/runner.py` (`resolve_roi`) |
| Un buen AUROC no implica buena calibración | Probabilidad con temperature scaling y zona de abstención | `pipeline/runner.py` (`analyze`) |
| Duplicados y casi duplicados en BUSI inflan las métricas | Huella exacta y perceptual al cargar; aviso de duplicado | `pipeline/quality.py`, `routers/cases.py` |
| La regla del protocolo es el promedio de logits de 5 semillas | El worker promedia logits y reporta la dispersión entre miembros | `pipeline/runner.py` |
| La cohorte de prueba ya estaba expuesta | La ficha del modelo declara procedencia y limitaciones; la validación final usará un conjunto nuevo | `model_card.json`, hoja de ruta |

## Componentes

```
┌──────────────┐     ┌─────────────────────────────┐     ┌────────────────┐
│ Frontend SPA │────▶│  API (FastAPI)              │────▶│ PostgreSQL     │
│ React + TS   │◀────│  sesiones JWT, roles, casos,│     │ (SQLite en     │
│ visor, ROI   │     │  registro de modelos        │     │  desarrollo)   │
└──────────────┘     └──────────┬──────────────────┘     └───────▲────────┘
                                │ escribe un análisis "pending"   │
                     ┌──────────▼──────────────────┐              │
                     │ Worker de inferencia        │──────────────┘
                     │ ONNX Runtime (CPU)          │     ┌────────────────┐
                     │ ROI→ensamble→calib.→CAM     │────▶│ Almacén        │
                     └─────────────────────────────┘     │ imágenes, CAM, │
                                                         │ bundles        │
                                                         └────────────────┘
```

- **API** (`backend/app/main.py`, `routers/`): valida, autoriza y registra en la bitácora. No
  ejecuta modelos, salvo en desarrollo (`inline_worker`).
- **Worker** (`backend/app/worker.py`): toma análisis pendientes de la tabla `analyses`, corre el
  pipeline y guarda el resultado. Ver [ADR 0002](adr/0002-cola-en-base-de-datos.md).
- **Pipeline** (`backend/app/pipeline/`): funciones puras sobre arreglos, sin base de datos ni
  HTTP, para poder probarlas y reutilizarlas en el módulo de auditoría.
- **Almacén** (`backend/app/storage.py`): disco local detrás de una interfaz de claves.
- **Frontend** (`frontend/src/`): no contiene lógica clínica; traduce los códigos del backend a
  texto (`labels.ts`).

## Flujo de un análisis

1. El médico sube un archivo. `imaging.decode_upload` lo decodifica y lo vuelve a codificar como
   PNG: así se descartan los metadatos. `quality` calcula las banderas de calidad y busca
   duplicados dentro del caso.
2. El médico traza (o no) un ROI y pide el análisis. La API valida el ROI, crea la fila en
   `analyses` con el modelo activo y responde `202`.
3. El worker reclama la fila con un `UPDATE` condicionado y ejecuta `runner.analyze`:
   recorte (ROI + margen de la ficha) → cada miembro del ensamble → promedio de logits →
   temperatura → dispersión entre miembros → distancia al vecino más cercano → decisión.
4. Decisión: si la imagen está fuera de dominio, eso prevalece; si no, la probabilidad calibrada
   se compara con la zona de abstención (`probably_benign`, `indeterminate`, `suspicious`).
5. El mapa de activación se guarda como PNG transparente y la interfaz lo superpone.

## Modelo de datos

`users` · `cases` (seudónimo, dueño) · `images` (hashes, banderas, duplicado de) ·
`model_versions` (ficha, hash, activo) · `analyses` (estado, ROI, resultados, modelo usado) ·
`audit_log` (quién, qué, cuándo; solo se agrega).

## Seguridad y privacidad

- Contraseñas con bcrypt; sesiones JWT de 8 horas guardadas en `sessionStorage`.
- Autorización por rol en cada ruta. Un caso ajeno responde `404`, no `403`, para no revelar que
  existe.
- No se almacena ningún dato identificable: el caso lleva un seudónimo y de la imagen solo quedan
  los píxeles. **Limitación:** el texto quemado en la imagen no se elimina.
- Fuera del entorno de desarrollo la aplicación no arranca con la clave por defecto.

## Límites conocidos

- Las tablas se crean al arrancar; todavía no hay migraciones (Alembic).
- Un análisis que queda en `running` porque el worker murió no se reencola solo.
- Al cargar se comprueban duplicados exactos y perceptuales dentro del caso. La auditoría compara los hashes de píxeles de todas las imágenes del CSV y rechaza repeticiones exactas entre casos. La búsqueda perceptual entre casos sigue pendiente.
- La inferencia es en CPU. Con ResNet-18 ×5 alcanza; habrá que medirlo con modelos mayores.

## Auditoría y localización

La auditoría recibe identificadores de análisis terminados y etiquetas binarias. Lee sus puntuaciones y la identidad del modelo desde la base, agrupa por seudónimo y registra el resumen, el autor y la huella del CSV en la bitácora. La descarga del PDF de cohorte requiere su autor o administración. El informe individual emplea el mismo control de acceso que el análisis.

El localizador ONNX procesa una imagen de 96 × 96 en escala de grises. La API devuelve la caja en coordenadas originales y registra la huella del localizador con la sugerencia. El médico puede sustituirla antes de solicitar el análisis. La fila del análisis conserva la región finalmente elegida.
