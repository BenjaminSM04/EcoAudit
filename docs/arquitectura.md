# Arquitectura

## Del estudio al sistema

Cada decisión de diseño responde a un hallazgo del estudio BUSI→BUS-BRA (protocolo v3).

| Hallazgo | Requisito | Dónde vive |
|---|---|---|
| Ninguna de las seis comparaciones primarias de adaptación (DANN, CORAL, MMD) superó al control | El sistema no promete adaptarse solo: mide cuánto se aleja la imagen de los datos de entrenamiento y avisa | `pipeline/bundle.py` (`shift_score`), `pipeline/runner.py` |
| El recorte de la lesión mejoró el AUROC en una comparación secundaria | El usuario puede trazar un ROI; la ficha del modelo declara si espera recorte o imagen completa | `ImageWorkspace.tsx`, `pipeline/runner.py` (`resolve_roi`) |
| Un buen AUROC no implica buena calibración | Probabilidad con temperature scaling y zona de abstención | `pipeline/runner.py` (`analyze`) |
| Duplicados y casi duplicados en BUSI inflan las métricas | Huella exacta y perceptual al cargar, dentro del caso y entre casos del mismo usuario; aviso de duplicado | `pipeline/quality.py`, `routers/cases.py` |
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
  pipeline y guarda el resultado. Un análisis que lleva más de 300 s en `running` se reencola; tras
  3 intentos queda `failed`. Ver [ADR 0002](adr/0002-cola-en-base-de-datos.md).
- **Pipeline** (`backend/app/pipeline/`): funciones puras sobre arreglos, sin base de datos ni
  HTTP, para poder probarlas y reutilizarlas en el módulo de auditoría.
- **Almacén** (`backend/app/storage.py`): disco local detrás de una interfaz de claves.
- **Frontend** (`frontend/src/`): no contiene lógica clínica; traduce los códigos del backend a
  texto (`labels.ts`).

## Flujo de un análisis

1. El médico sube un archivo. `imaging.decode_upload` lo decodifica y lo vuelve a codificar como
   PNG: así se descartan los metadatos. `quality` calcula las banderas de calidad y busca
   duplicados dentro del caso y entre casos del mismo usuario.
2. El médico traza (o no) un ROI y pide el análisis. La API valida el ROI, crea la fila en
   `analyses` con el modelo activo y responde `202`.
3. El worker reclama la fila con un `UPDATE` condicionado y ejecuta `runner.analyze`:
   recorte (ROI + margen de la ficha) → cada miembro del ensamble → promedio de logits →
   temperatura → dispersión entre miembros → distancia al vecino más cercano → decisión.
4. Decisión: si la imagen está fuera de dominio, eso prevalece; si no, la probabilidad calibrada
   se compara con la zona de abstención (`probably_benign`, `indeterminate`, `suspicious`).
5. El mapa de activación se guarda como PNG transparente y la interfaz lo superpone.

## Modelo de datos

`users` (`password_changed_at`) · `cases` (seudónimo, dueño) · `images` (hashes, banderas,
duplicado de) · `model_versions` (ficha, hash, activo) · `analyses` (estado, ROI, resultados,
modelo usado, `attempts`) · `cohorts` (nombre, origen `analyses` o `batch`, estado, modelo,
progreso, dueño) · `cohort_items` (análisis y etiqueta de cada miembro) · `audit_log` (quién, qué,
cuándo; solo se agrega).

## Seguridad y privacidad

- Contraseñas con bcrypt; sesiones JWT de 8 horas guardadas en `sessionStorage`.
- Cambiar la contraseña, propia o restablecida por un administrador, invalida los tokens emitidos
  antes. La interfaz pide volver a ingresar.
- Cinco fallos de ingreso para un mismo correo en 15 minutos responden `429`, aunque la contraseña
  sea correcta. El conteo se hace sobre la bitácora.
- Autorización por rol en cada ruta. El médico accede a sus casos y no a las cohortes (`403`); el
  investigador, a sus casos y cohortes; el administrador, a todo. Un recurso ajeno responde `404`,
  no `403`, para no revelar que existe. El informe individual de un análisis usa el mismo control
  de acceso.
- No se almacena ningún dato identificable: el caso lleva un seudónimo y de la imagen solo quedan
  los píxeles. **Limitación:** el texto quemado en la imagen no se elimina.
- Fuera del entorno de desarrollo la aplicación no arranca con la clave por defecto.

## Límites conocidos

- Las tablas se crean al arrancar; las migraciones con Alembic están en curso.
- Los duplicados entre casos solo se detectan dentro de la cuenta: una imagen repetida en casos de usuarios distintos no se marca.
- La inferencia es en CPU. Con ResNet-18 ×5 alcanza; habrá que medirlo con modelos mayores.

## Auditoría de cohortes

Una cohorte agrupa análisis terminados, cada uno con una etiqueta binaria, y calcula sus métricas
por paciente. Tiene dos orígenes:

- **Desde análisis existentes.** Se sube un CSV `analysis_id,label`. Cada análisis debe estar
  terminado, pertenecer al usuario (el administrador puede usar cualquiera) y usar la misma versión
  de modelo. Si una fila no cumple, la carga responde `422` con su número, sin revelar si el análisis
  existe.
- **Por lote nuevo.** Se sube un manifiesto `filename,patient_ref,label` con las imágenes, hasta
  1000. Requiere modelo activo (`409` si no hay). Todo se valida antes de guardar nada. Se crea un
  caso por `patient_ref`, cada imagen pasa por la misma de-identificación y control de calidad, y se
  encola un análisis de imagen completa por imagen.

En el lote, la cohorte queda en `processing` hasta que todos sus análisis terminan; entonces el
resultado se calcula al consultarla. Si alguno falla, queda `failed`. La cohorte guarda la huella
del modelo y la del CSV. Ofrece un informe PDF (solo si está `done`) y un CSV de ítems con
`analysis_id,patient_ref,label,probability,decision,status`.

## Localización

El localizador ONNX procesa una imagen de 96 × 96 en escala de grises. La API devuelve la caja en coordenadas originales y registra la huella del localizador con la sugerencia. El médico puede sustituirla antes de solicitar el análisis. La fila del análisis conserva la región finalmente elegida.
