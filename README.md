# EcoAudit

Plataforma web de apoyo a la clasificación de lesiones mamarias en ecografía, con detección de
cambio de dominio, probabilidad calibrada con abstención y trazabilidad del modelo.

Proyecto de grado de Ingeniería de Sistemas. Nace de los hallazgos del estudio de generalización
BUSI→BUS-BRA (repositorio `busgen`), que aquí se convierten en requisitos de diseño.

> **Prototipo de investigación.** No es un dispositivo médico, no fue validado clínicamente y no
> debe usarse para decidir la atención de un paciente.

## Qué hace hoy

- Usuarios con tres roles (médico, investigador, administrador) y bitácora de acciones.
- Casos identificados con un seudónimo; un médico solo ve los suyos.
- Carga de PNG, JPEG, BMP, TIFF y DICOM sin compresión. Solo se conservan los píxeles: los
  metadatos (EXIF, etiquetas DICOM) se descartan.
- Control de calidad al cargar: resolución, contraste, color y duplicados dentro del caso.
- Análisis de la imagen completa o de un ROI trazado por el usuario: ensamble de modelos ONNX,
  probabilidad calibrada, zona de abstención, alerta de imagen fuera de dominio y mapa de
  activación.
- Registro de modelos: cada versión es un paquete inmutable con su ficha y su hash; todo análisis
  queda ligado a la versión que lo produjo.

- Auditoría de cohortes etiquetadas en CSV para investigadores y administradores, con AUROC e intervalo por paciente, calibración e informe PDF.
- Sugerencia experimental de ROI aprendida de máscaras. El usuario revisa la propuesta antes de solicitar el análisis. Cada resultado terminado admite descarga en PDF.

El [manuscrito de tesis](tesis/EcoAudit.docx) contiene el protocolo, los resultados y sus límites.
La [guía de reproducción](tesis/README.md) explica cómo repetir el experimento y usar la auditoría.
Lo que falta está en [docs/roadmap.md](docs/roadmap.md).

## Estructura

| Carpeta | Contenido |
|---|---|
| `backend/` | API (FastAPI), pipeline de inferencia y worker |
| `frontend/` | Interfaz web (React + TypeScript + Vite) |
| `ml/` | Exportación y, más adelante, entrenamiento de modelos |
| `docs/` | Arquitectura, contrato del bundle, decisiones (ADR), hoja de ruta |
| `tesis/` | Documento del proyecto de grado |

## Puesta en marcha para desarrollo

Requisitos: Python 3.11 y Node 24.

```bash
# 1) Backend
cd backend
python -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install -e ".[dev]"

python -m app.cli create-user --email admin@ecoaudit.local --name "Administrador" --role admin
python -m app.cli create-user --email medico@ecoaudit.local --name "Médico" --role medico

# Un modelo para poder analizar. El de demostración no está entrenado: solo sirve para
# recorrer el flujo. Para un modelo real, vea ml/README.md.
python -m app.cli make-demo-bundle data/bundles/demo
python -m app.cli register-model data/bundles/demo --activate

uvicorn app.main:app --reload     # http://localhost:8000/docs

# 2) Frontend, en otra terminal
cd frontend
npm install
npm run dev                       # http://localhost:5173
```

En desarrollo la base de datos es SQLite (`backend/data/`) y el análisis corre dentro del proceso
de la API. Para separar el worker: `ECOAUDIT_INLINE_WORKER=false` y `python -m app.worker`.
Con el worker inline, al arrancar la API se procesan en segundo plano los análisis que quedaron
pendientes.

### Migraciones de la base de datos

El esquema lo gestiona Alembic (`backend/alembic.ini`, `backend/migrations/`). La API, el worker y
la CLI aplican las migraciones pendientes al arrancar; también se pueden aplicar a mano con
`python -m app.cli db-upgrade`. Un cambio en `app/models.py` va acompañado de una migración nueva
escrita a mano (`alembic revision -m "descripción"`, desde `backend/`).

Una base creada antes de Alembic (sin la tabla `alembic_version`) se adopta una sola vez: se crean
las tablas que faltan, se agregan las columnas ausentes que admitan NULL o tengan valor por
defecto, y se marca la base como `0001`. Si falta una columna obligatoria sin valor por defecto,
el arranque falla con un mensaje claro y no modifica nada. Detalles y límites en
`backend/app/migrate.py`.

## Pruebas

```bash
cd backend  && pytest -q && ruff check .
cd frontend && npm run lint && npm run build
```

## Despliegue con Docker

```bash
cp .env.example .env              # complete las dos variables
docker compose up --build         # interfaz en http://localhost:8080
docker compose exec api python -m app.cli create-user --email ... --name ... --role admin
```

Levanta PostgreSQL, la API, el worker y la interfaz detrás de nginx.
