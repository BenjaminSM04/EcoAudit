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

Desde la raíz, copie `.env.example` a `.env` en una instalación nueva y complete sus dos valores. Mantenga las credenciales fuera del control de versiones. Genere la clave de firma con un generador criptográfico y use una contraseña de PostgreSQL apta para la URL construida por Compose o codificada para ese uso según la configuración operativa.

```powershell
Copy-Item .env.example .env
# Complete .env antes de iniciar.
docker compose up -d --build
docker compose ps
docker compose exec api python -m app.cli db-upgrade
docker compose exec api python -m app.cli create-user --email admin@ecoaudit.local --name "Administrador" --role admin
```

Compose inicia `db` (PostgreSQL 16), `api`, `worker` y `web` (nginx). Publica HTTP en 8080. Comparte `storage` entre API y worker, con el almacén efectivo en `/data/storage`. `pgdata` contiene los datos del motor. Valide `http://localhost:8080/api/health` y haga un análisis de humo desde la interfaz.

Para una demostración completa, use una instancia de ensayo con sus propios volúmenes. Con `ECOAUDIT_DEMO=1`, Compose compila la API y el worker con el extra `demo`, que incorpora `onnx`. El valor predeterminado es `0`. Una vez sana la API, cargue el bundle, las cuentas y los casos sintéticos con una contraseña de al menos 10 caracteres.

```bash
ECOAUDIT_DEMO=1 docker compose up --build -d
docker compose exec api python -m app.cli seed-demo --password 'CAMBIE-ESTA-CLAVE'
```

En PowerShell, ejecute `$env:ECOAUDIT_DEMO = '1'` antes de `docker compose up --build -d`. Inicie sesión en `http://localhost:8080` con `admin@ecoaudit.test`, `medico1@ecoaudit.test`, `medico2@ecoaudit.test` o `investigador@ecoaudit.test`. Para generar únicamente el bundle, ejecute `docker compose exec api python -m app.cli make-demo-bundle /tmp/ecoaudit-demo`.

## Configuración

| Variable | Valor base y uso |
| --- | --- |
| `POSTGRES_PASSWORD` | Obligatoria en Compose. Se utiliza en la inicialización y conexión a PostgreSQL. |
| `ECOAUDIT_DEMO` | Argumento de compilación de Compose. `1` instala el extra `demo`; el valor predeterminado es `0`. |
| `ECOAUDIT_SECRET_KEY` | Firma JWT. Defina una clave propia en despliegue. Fuera de `dev` se rechaza la predeterminada. El receptor STOW visible también la usa para derivar seudónimos. |
| `ECOAUDIT_ENVIRONMENT` | `dev` por defecto; Compose usa `prod`. |
| `ECOAUDIT_DATABASE_URL` | `sqlite:///./data/ecoaudit.db` por defecto. Compose usa `postgresql+psycopg` hacia `db:5432/ecoaudit`. |
| `ECOAUDIT_STORAGE_DIR` | `./data/storage` por defecto; la imagen backend usa `/data/storage`. |
| `ECOAUDIT_ACCESS_TOKEN_MINUTES` | 480 minutos por defecto. |
| `ECOAUDIT_CORS_ORIGINS` | `http://localhost:5173` por defecto. Admite una lista separada por comas. Compose usa `http://localhost:8080` y el override HTTPS usa el origen de `ECOAUDIT_DOMAIN`. |
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

Desde la raíz del repositorio, con PostgreSQL activo, ejecute el par de scripts para su sistema. El respaldo crea un directorio fechado en UTC con `postgres.dump` (formato personalizado de PostgreSQL) y `storage.tar.gz` (volumen `storage` completo). Seleccione un destino local fuera del repositorio, con acceso restringido y espacio para ambos archivos.

```powershell
.\tools\respaldo.ps1 -Destino 'D:\Respaldos\EcoAudit'
.\tools\restaurar.ps1 -Destino 'D:\Respaldos\EcoAudit\AAAAMMDDTHHMMSSZ-identificador'
```

```bash
bash tools/respaldo.sh /srv/respaldos/ecoaudit
bash tools/restaurar.sh /srv/respaldos/ecoaudit/AAAAMMDDTHHMMSSZ-identificador
```

Indique el directorio concreto que devuelve el script de respaldo. Use los archivos Compose y el proyecto del despliegue. Para HTTPS, defina `COMPOSE_FILE` como `docker-compose.yml:deploy/docker-compose.https.yml` en Linux, o `docker-compose.yml;deploy/docker-compose.https.yml` con el cliente Docker de Windows. Mantenga disponibles las variables del proyecto.

En una estación Windows donde se permita ejecutar scripts locales con `RemoteSigned`, puede iniciar el proceso con `powershell -NoProfile -ExecutionPolicy RemoteSigned -File .\tools\respaldo.ps1 -Destino 'D:\Respaldos\EcoAudit'`. Use la misma opción de proceso para restaurar si corresponde.

Antes de operar, cierre el ingreso de tráfico, deje que el worker termine los análisis pendientes y detenga los procesos externos que escriban en la base o el volumen. Coordine una operación a la vez por proyecto. Los scripts detienen nginx, API y worker y, al terminar correctamente, arrancan los servicios que estaban activos. Caddy puede seguir escuchando en los puertos publicados durante el mantenimiento. Custodie el par de archivos cifrado y gestione las claves y la configuración por el canal institucional.

**Restaurar reemplaza la base `ecoaudit` y el contenido del volumen de archivos del proyecto seleccionado.** Use un respaldo de confianza y ensaye primero en una instancia aislada. Los scripts inspeccionan ambos archivos antes de reemplazar los datos, recrean la base y recuperan los archivos con sus permisos. Si falla una restauración tras la pausa, revise el error con los escritores detenidos. Antes de reabrir el tráfico, compruebe revisión de Alembic, conteos, acceso a casos e imágenes, huellas de archivos y un análisis de humo. Registre RPO y RTO. Para SQLite, detenga los escritores y use la API de backup de SQLite o copie la base cerrada, incluidos los archivos auxiliares correspondientes, junto con su almacén.

## HTTPS mediante Caddy

Use Docker Compose v2.24.4 o posterior. Defina `ECOAUDIT_DOMAIN` en `.env` con el nombre DNS que usarán los clientes, sin esquema, ruta ni puerto. Seleccione `ECOAUDIT_TLS_MODE=publico` para un dominio público o `ECOAUDIT_TLS_MODE=interno` para la red hospitalaria. Arranque desde la raíz del repositorio.

```powershell
docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml config -q
docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml up -d --build
docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml ps
```

El override retira la publicación de nginx en 8080. Caddy publica 80 y 443, redirige HTTP a HTTPS y reenvía a nginx por la red de Compose. PostgreSQL, nginx y la API quedan en la red interna. Limite el acceso a los puertos publicados al ámbito de la instalación. Conserve `caddy_data` para mantener la autoridad local y su material criptográfico o el estado de renovación, según el modo. [HTTPS automático de Caddy](https://caddyserver.com/docs/automatic-https) · [Combinación de archivos Compose](https://docs.docker.com/reference/compose-file/merge/)

- **Público.** Configure el DNS público hacia el servidor y habilite el acceso a 80 y 443 para la validación ACME. Caddy solicita y renueva el certificado.
- **Interno.** Configure el DNS hospitalario hacia el servidor. Con `tls internal`, Caddy emite certificados con su autoridad local. Exporte solo el certificado público mediante `docker compose -f docker-compose.yml -f deploy/docker-compose.https.yml cp caddy:/data/caddy/pki/authorities/local/root.crt ./ecoaudit-ca.crt`. Distribúyalo por el canal institucional e instálelo en los almacenes de confianza de los clientes autorizados. Para una instalación sin internet, precargue las imágenes de EcoAudit, PostgreSQL y Caddy. Use `up -d --no-build --pull never` con los mismos dos archivos Compose. La interfaz usa su fuente de respaldo cuando Google Fonts no está disponible.

Verifique la redirección, el certificado y `https://<dominio>/api/health` desde un cliente que confíe en la autoridad elegida. nginx admite cuerpos de hasta 30 MiB en general (25 MiB por imagen más multipart), 100 MiB para STOW-RS y 256 MiB para lotes de cohortes. Divida los lotes que superen ese tamaño. Si cambia el límite de la API, revise el de nginx y el del proxy institucional.

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
