# Manual técnico

## Desarrollo local

Desde la raíz en PowerShell, con Python 3.11 y Node 24:

```powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m app.cli db-upgrade
python -m app.cli create-user --email admin@ecoaudit.local --name "Administrador" --role admin
python -m app.cli create-user --email medico@ecoaudit.local --name "Médico" --role medico
python -m app.cli make-demo-bundle data/bundles/demo
python -m app.cli register-model data/bundles/demo --activate
uvicorn app.main:app --reload
```

En otra terminal, desde la raíz:

```powershell
Set-Location frontend
npm ci
npm run dev
```

La interfaz local usa `http://localhost:5173` y Vite reenvía `/api` a `http://127.0.0.1:8000`. Para cambiar el destino, configure `ECOAUDIT_API_PROXY` al iniciar Vite. Consulte `/api/health` y, en desarrollo, la documentación OpenAPI en `/docs` de la API. SQLite y los archivos se crean relativos al directorio de ejecución del backend. El paquete de demostración carece de entrenamiento.

## Docker Compose

Desde la raíz, copie `.env.example` a `.env` en una instalación nueva y complete sus dos valores. Mantenga las credenciales fuera del control de versiones. Use una clave generada con `python -c "import secrets; print(secrets.token_urlsafe(48))"` y una contraseña de PostgreSQL apta para la URL construida por Compose o codificada para ese uso según la configuración operativa.

```powershell
Copy-Item .env.example .env
# Complete .env antes de iniciar.
docker compose up -d --build
docker compose ps
docker compose exec api python -m app.cli db-upgrade
docker compose exec api python -m app.cli create-user --email admin@ecoaudit.local --name "Administrador" --role admin
```

Compose inicia `db` (PostgreSQL 16), `api`, `worker` y `web` (nginx). Publica HTTP en 8080. Comparte `storage` entre API y worker, con el almacén efectivo en `/data/storage`. `pgdata` contiene los datos del motor. Valide `http://localhost:8080/api/health` y haga un análisis de humo desde la interfaz.

## Configuración

| Variable | Valor base y uso |
| --- | --- |
| `POSTGRES_PASSWORD` | Obligatoria en Compose. Se utiliza en la inicialización y conexión a PostgreSQL. |
| `ECOAUDIT_SECRET_KEY` | Firma JWT. Defina una clave propia en despliegue. Fuera de `dev` se rechaza la predeterminada. El receptor STOW visible también la usa para derivar seudónimos. |
| `ECOAUDIT_ENVIRONMENT` | `dev` por defecto; Compose usa `prod`. |
| `ECOAUDIT_DATABASE_URL` | `sqlite:///./data/ecoaudit.db` por defecto. Compose usa `postgresql+psycopg` hacia `db:5432/ecoaudit`. |
| `ECOAUDIT_STORAGE_DIR` | `./data/storage` por defecto; la imagen backend usa `/data/storage`. |
| `ECOAUDIT_ACCESS_TOKEN_MINUTES` | 480 minutos por defecto. |
| `ECOAUDIT_CORS_ORIGINS` | `http://localhost:5173` por defecto; lista separada por comas. Compose fija `http://localhost:8080`. |
| `ECOAUDIT_MAX_UPLOAD_MB` | 25 por defecto, convertido a bytes multiplicando por 1024². Revise también límites de lote y proxy. |
| `ECOAUDIT_INLINE_WORKER` | `true` en desarrollo y `false` en Compose. |
| `ECOAUDIT_WORKER_POLL_SECONDS` | 1 s de espera por defecto cuando no hay trabajo. |
| `ECOAUDIT_ANALYSIS_TIMEOUT_SECONDS` | 300 s por defecto para recuperar análisis en ejecución vencidos. |

En desarrollo, `Settings` carga también `.env` desde el directorio de ejecución. En Compose las variables de backend deben entrar efectivamente al entorno de sus contenedores mediante el archivo Compose o una configuración de despliegue. El `.env` de la raíz sirve para la interpolación de Compose.

## Migraciones, modelo y worker

- **Migraciones.** API, CLI y worker aplican Alembic durante el arranque según su punto de entrada. `python -m app.cli db-upgrade` informa la revisión. `0001` es la base y `0002_lecturas_clinicas.py` incorpora `clinical_readings` en I4. Una base previa a Alembic se adopta bajo las reglas de `migrate.py`. Ensaye sobre una copia, confirme revisión y realice respaldo antes de actualizar.
- **Registro.** Prepare `model_card.json`, ONNX y cabezas NPZ y, cuando corresponda, referencia de dominio. Consulte el [contrato del bundle](../model-bundle.md) y el [exportador](../../ml/README.md). Para Docker, copie un paquete autorizado a una ruta legible del contenedor, por ejemplo `docker compose cp ./bundle api:/tmp/ecoaudit-bundle`. Ejecute `docker compose exec api python -m app.cli register-model /tmp/ecoaudit-bundle`. Agregue `--activate` para activación inmediata o active después en **Modelos**. Conserve los archivos y coteje SHA-256. El registro no sustituye la validación científica.
- **Localizador.** Copie pesos autorizados a `roi/segmenter.onnx` dentro del almacén. Compruebe lectura por el usuario del servicio y la huella registrada al sugerir ROI. El clasificador tiene un registro independiente.
- **Worker.** Para separarlo en desarrollo fije `$env:ECOAUDIT_INLINE_WORKER = "false"` antes de arrancar uvicorn. En otra terminal, desde `backend/` y con el mismo entorno de base y almacén, ejecute `python -m app.worker`. En Compose inspeccione `docker compose logs worker api`. Verifique transición `pending` → `running` → `done` y revise `attempts` y tiempos ante una interrupción.

## Respaldo y restauración

Realice el ensayo en una instancia desechable. Para obtener un punto consistente, interrumpa el ingreso al sistema y detenga los escritores web, API y worker. PostgreSQL permanece disponible para el volcado. Desde la raíz, los comandos guardan un archivo binario de PostgreSQL sin pasarlo por la redirección textual de PowerShell:

```powershell
docker compose stop web api worker
docker compose exec -T db pg_dump -U ecoaudit -d ecoaudit -Fc -f /tmp/ecoaudit.dump
docker compose cp db:/tmp/ecoaudit.dump ./ecoaudit.dump
docker compose cp api:/data/storage ./respaldo-storage
docker compose start api worker web
```

Compruebe los códigos de salida y la estructura del directorio copiado antes de reabrir el servicio. Registre fecha UTC, revisión, huellas, conteos y metadatos del respaldo. Custodie cifrados el volcado y archivos y conserve las claves y configuración por el canal institucional. Elimine copias temporales conforme al procedimiento de retención. Para SQLite, detenga API y worker antes de copiar; use la API de backup de SQLite o copie la base cerrada incluyendo los archivos auxiliares si existen, junto con su almacén.

Para restaurar Compose, use una instancia aislada con base y almacén vacíos. Arranque solo `db`. Copie el volcado al contenedor con `docker compose cp ./ecoaudit.dump db:/tmp/ecoaudit.dump` y ejecute `docker compose exec -T db pg_restore -U ecoaudit -d ecoaudit --exit-on-error /tmp/ecoaudit.dump`. Con la API creada pero detenida, copie el contenido de `respaldo-storage` a `/data/storage` en el volumen compartido. Verifique permisos del usuario `ecoaudit`, fichas y hashes, rutas de imágenes/CAM y conteos. Arranque API y worker y efectúe humo con una cuenta de prueba. Registre RPO/RTO. Evite abrir tráfico hasta comprobar la coherencia entre base y almacén.

## HTTPS mediante proxy inverso

Configure HTTPS en el proxy institucional y limite el upstream HTTP de nginx web a loopback o a una red interna del proxy. En Compose de ensayo, el ajuste de publicación puede usar `127.0.0.1:8080:80` para un proxy en el mismo host. Exponga 443 al ámbito autorizado y configure certificados, redirección HTTP y renovación a cargo del operador. Conserve las rutas `/api/` y el encabezado `Host`. Use el origen HTTPS de la SPA si su despliegue necesita CORS. Mantenga API y BD en red privada. Revise límites y tiempos en ambos proxies. El nginx incluido fija `client_max_body_size 30m` y puede rechazar lotes o un multipart STOW permitido por la API. Haga prueba de carga y confirmación de límites en la configuración resultante.

## Conexión PACS · DICOMweb STOW-RS I4

1. Configure un PACS de ensayo o pasarela para `POST /api/dicomweb/studies`. El backend visible exige Bearer de médico o administrador. Use una cuenta dedicada bajo la política local.
2. Envíe `application/dicom` o `multipart/related; type="application/dicom"; boundary=…` con partes `application/dicom`. Use DICOM de prueba sin compresión, con `PatientID` ficticio y píxeles revisados. El receptor admite hasta 100 partes, un límite por instancia y hasta cuatro veces ese límite para el cuerpo multipart. Para DICOM multicuadro, el decodificador conserva el primer cuadro.
3. El receptor deriva un seudónimo `PAC-…` mediante HMAC del `PatientID` y agrupa por seudónimo y dueño. Verifique el impacto de rotar la clave o cambiar de cuenta, ya que afecta la correspondencia. El DICOM se reconstruye como PNG y la recepción deja avisos de calidad y bitácora.
4. Concilie el JSON local (`instancias`, `fallos`) y el estado `200` completo, `202` parcial o `400` sin instancias aceptadas. `413` indica exceso de tamaño y `415` un tipo no admitido. La respuesta específica exige prueba con el PACS o adaptación en la pasarela. Un reenvío puede generar una imagen marcada como duplicada. [DICOM PS3.18, Store Transaction](https://dicom.nema.org/medical/dicom/2024d/output/chtml/part18/sect_10.5.html)

## Conexión HCE · HL7 FHIR R4 I4

1. Con Bearer autorizado, solicite `GET /api/analyses/{analysis_id}/fhir` sobre un análisis `done`. El servidor devuelve `application/fhir+json` y registra `analysis_fhir_exported`. El acceso a recursos sigue el ámbito de casos.
2. Valide el `Bundle` de tipo `collection` como R4 4.0.1. El código visible incluye `Patient` con seudónimo, `Device` con identificación del modelo, `Observation` y `DiagnosticReport` con advertencia de investigación. El administrador puede recibir todas las lecturas asociadas; otros roles solo la propia.
3. Aplique el perfil del receptor en una HCE de ensayo. Quite del proceso cualquier correspondencia con pacientes reales hasta contar con autorización y un acuerdo de identificación. La descarga se integra mediante un consumidor externo. [HL7 FHIR R4, DiagnosticReport](https://www.hl7.org/fhir/R4/diagnosticreport.html)

Consulte las muestras de solicitud y los contratos de estadísticas, bitácora y comparación en la [API hospitalaria](../api-hospitalaria.md).

## Solución de problemas

| Síntoma | Comprobación |
| --- | --- |
| API no arranca | Revise URL, disponibilidad de PostgreSQL, permisos y error de migración o clave predeterminada. |
| `401` tras cambio de contraseña | Inicie sesión otra vez y use un token nuevo. |
| `429` al ingresar | Verifique la ventana de 15 min y los eventos del correo normalizado. |
| Carga `413` / `422` | Compruebe límites en nginx y API, formato, sintaxis DICOM y calidad del manifiesto. |
| Análisis `409` o sugerencia `503` | Verifique versión activa o instalación y permisos del localizador, respectivamente. |
| Cola sin progreso | Verifique modo del worker, acceso al volumen y a la misma base, estado, antigüedad y registros del worker. |
| Resultado sin mapa o error de lectura | Coteje `cam_key`, permisos y coherencia del respaldo restaurado. |
| Integración rechazada | Coteje rol y ámbito, cuerpo STOW, respuesta por instancia y validador/perfil FHIR. |
