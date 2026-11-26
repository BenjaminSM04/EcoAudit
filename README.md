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
- Panel de indicadores: actividad, distribución de decisiones, tasa de abstención, alertas de dominio y latencia.
- Lectura clínica BI-RADS ciega antes de ver el resultado del modelo y concordancia médico–modelo (kappa de Cohen).
- Integración hospitalaria: exportación HL7 FHIR R4 de cada análisis y recepción DICOMweb (STOW-RS) desde PACS o ecógrafo, con seudónimo derivado de PatientID ([API hospitalaria](docs/api-hospitalaria.md)).
- Reanálisis de una cohorte con otra versión de modelo y comparación pareada de AUROC.
- Bitácora consultable y exportable para administradores.
- Interfaz rediseñada con un sistema de diseño propio en tonos rosa, adaptable a móvil.

La [documentación de ingeniería](docs/ingenieria/README.md) reúne requisitos, casos de uso, modelado (C4, ER, secuencias), trazabilidad, metodología Scrum, plan de pruebas, evaluación ISO/IEC 25010, protocolo SUS, manuales y la propuesta para hospitales.

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

Pruebas de extremo a extremo (Playwright, Chromium) contra el frontend y el backend reales, con
un modelo de demostración. Necesitan el backend instalado (`pip install -e "backend[dev]"`) y las
dependencias del frontend (`npm ci`):

```bash
cd e2e
npm ci
npx playwright install chromium   # solo la primera vez
npm test
```

Las pruebas arrancan por su cuenta el backend (puerto 8001) y Vite (puerto 5174) con una base y un
almacenamiento nuevos en `e2e/.tmp/` (se borra en cada ejecución), crean los usuarios de prueba con
contraseñas aleatorias y registran el modelo de demostración. No tocan `backend/data/`.

## Demo para la feria en Windows 11

### Docker Desktop (recomendado por el autor)

1. Instala Git y Docker Desktop con `winget install Git.Git` y
   `winget install Docker.DockerDesktop`. Si necesitas WSL 2, ejecuta `wsl --install` como
   administrador. Reinicia Windows, abre Docker Desktop y acepta sus términos.
2. Clona EcoAudit con `git clone https://github.com/BenjaminSM04/EcoAudit.git` en una carpeta de
   tu usuario en `C:`. Desde el clon, abre `tools\feria\docker-demo.cmd` con internet. El script
   compila las imágenes Docker y descarga y verifica los ZIP del modelo y las ecografías. Si el
   clon aún carece de los scripts, copia los archivos de la entrega según la
   [guía de la feria](tools/feria/README.md).
3. Abre <http://localhost:8080> con las cuentas de
   `%LOCALAPPDATA%\EcoAuditFeria\credenciales-docker.txt`. Usa `docker-detener.cmd` para detener
   los servicios y conservar sus datos.
4. Guarda el clon, los volúmenes, las imágenes Docker y los ZIP en la laptop. Ensaya con el
   Wi-Fi apagado usando `.\tools\feria\docker-demo.cmd -SinCompilar` desde la raíz del clon.
   La interfaz y la inferencia se ejecutan localmente. También puedes reanudar con
   `docker compose up -d` si usaste el puerto predeterminado.

### Sin Docker (respaldo)

1. Instala Python y Node.js según la [guía de la feria](tools/feria/README.md) y prepara el clon
   con `tools\feria\preparar.cmd`, indicando la carpeta del modelo ONNX del estudio.
2. Usa `iniciar.cmd` para abrir la demo local y `detener.cmd` para cerrarla. La guía también
   explica cómo usar ZIP locales y un puerto alternativo con Docker.

## Despliegue con Docker

```bash
cp .env.example .env              # complete las dos variables
docker compose up --build         # interfaz en http://localhost:8080
docker compose exec api python -m app.cli create-user --email ... --name ... --role admin
```

Levanta PostgreSQL, la API, el worker y la interfaz detrás de nginx.

Para preparar una demostración completa en una instancia de ensayo, compile con el extra
`demo` y cargue el modelo y los casos sintéticos. Sustituya el ejemplo por una contraseña
de al menos 10 caracteres.

```bash
ECOAUDIT_DEMO=1 docker compose up --build -d
docker compose exec api python -m app.cli seed-demo --password 'CAMBIE-ESTA-CLAVE'
```

En PowerShell, ejecute `$env:ECOAUDIT_DEMO = '1'` antes de `docker compose up --build -d`.
Las cuentas de ensayo son `admin@ecoaudit.test`, `medico1@ecoaudit.test`,
`medico2@ecoaudit.test` e `investigador@ecoaudit.test`.
