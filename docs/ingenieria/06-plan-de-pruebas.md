# Plan de pruebas

## Preparación y ejecución automatizada

Use una instalación aislada con imágenes y cuentas ficticias. Registre revisión, plataforma, versión de dependencias, motor de base de datos, modo de worker y SHA-256 del modelo. El modelo de demostración permite ejercitar el sistema y no aporta evidencia de desempeño clínico.

Desde `backend/`, con Python 3.11 y el entorno virtual activo:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_pipeline.py tests/test_cohorts.py
python -m pytest -q --cov=app --cov-report=term --cov-report=xml
ruff check .
ruff format --check .
```

El job `backend` de CI publica `backend/coverage.xml` como artefacto `cobertura-backend`. El job `docker` ejecuta `docker compose build` para comprobar la construcción de las imágenes.

El 23 de noviembre de 2026, la suite local aprobó 120 pruebas y cubrió 2456 de 2670 líneas de `app` (91,99 %). [Informe de cobertura](resultados/cobertura-2026-11-23.md)

La primera selección cubre decodificación, ROI, bundle, reglas de decisión y métricas. `test_cohorts.py` incluye también un caso API. La suite completa cubre integración mediante TestClient, almacenamiento temporal y un bundle de demostración. Compruebe cuentas, aislamiento, reencolado, migraciones y consistencia de lote. Para verificar de forma focalizada el código I4 visible, ejecute desde `backend/`:

```powershell
python -m pytest -q tests/test_hospital.py tests/test_dicomweb.py tests/test_cohort_analyses.py
```

Desde `frontend/`, con Node 24:

```powershell
npm ci
npm run lint
npm run build
```

Desde `e2e/`, con Python que pueda importar el backend instalado y las dependencias del frontend listas:

```powershell
npm ci
npx playwright install chromium
npm test
npx playwright show-report
```

La configuración inicia Vite en 5174 y la API en 8001, usa Chromium con un trabajador y recrea `e2e/.tmp/`. El informe HTML queda en `playwright-report/` y conserva trazas y capturas de fallos conforme a la configuración. Los recorridos cubren ingreso, cuenta, casos, visor, auditoría, administración y aislamiento. La [matriz de trazabilidad](04-trazabilidad.md) identifica las pruebas aplicables. Ejecute también el humo de Compose con PostgreSQL, incluyendo una parada del worker y recuperación del trabajo bajo condiciones controladas.

## Carga y latencia

Para reproducir el ensayo exploratorio de 1, 5 y 10 usuarios concurrentes, prepare el stack de prueba con un bundle de demostración activo y una cuenta ficticia. Defina `ECOAUDIT_CARGA_EMAIL` y `ECOAUDIT_CARGA_PASSWORD` en el entorno del cliente. Desde la raíz, con el entorno de desarrollo del backend activo:

```powershell
python tools/carga/prueba_carga.py --url http://localhost:8080 --repeticiones 3 --informe ./carga-local.md
```

El cliente crea casos sintéticos, sube un PNG por sesión y espera el resultado. Use una base de ensayo y mantenga sus agregados separados. El [informe del 23 de noviembre](resultados/carga-2026-11-23.md) documenta este perfil exploratorio.

Para el perfil extendido de aceptación:

1. En un Compose aislado, anote CPU, RAM, almacenamiento, concurrencia y el modelo versionado que se va a ensayar. Use un worker, PNG de prueba de tamaño fijo y un conjunto congelado de entradas. Realice diez análisis de calentamiento. Use una base o un ámbito separado para la medición y mantenga el calentamiento fuera de los agregados.
2. Con k6 o un cliente HTTP equivalente en un directorio de ensayos, autentique cuatro cuentas o clientes autorizados. Prepare imágenes. Envíe 100 solicitudes de análisis repartidas entre los cuatro clientes, con una operación en curso por cliente. Sondee cada segundo hasta obtener la condición terminal, con límite de 60 s por solicitud. Registre códigos, estados y plazos excedidos.
3. Como investigador o administrador, coteje los 100 identificadores con `GET /api/stats/performance` en I4. Si el agregado incorpora otros resultados, calcule tiempos por fila en la base de ensayo con las marcas `created_at`, `started_at` y `finished_at`. Para percentiles use interpolación lineal y reporte el número de observaciones. Mida por separado el tiempo externo incluyendo el sondeo. Registre errores y plazos excedidos en el total intentado, aunque falten en el agregado de finalizados.
4. Repita tres veces, con datos o ámbitos equivalentes. Como prueba de capacidad de lote, envíe 1000 imágenes ficticias aptas dentro de los límites del proxy acordados, mida el tiempo de admisión y de finalización y concilie el CSV. Un lote de 1001 debe rechazarse. Los umbrales de desempeño individual no se aplican al tiempo total de un lote.

Criterios propuestos por corrida para el perfil individual: p95 de servicio ≤ 5 s, p95 desde creación hasta finalización ≤ 15 s y ≤ 1 % de fallos o vencimientos. Conserve el p95 observado en cliente como medida complementaria.

## Seguridad, interoperabilidad y usabilidad

| Área | Ejecución | Evidencia |
| --- | --- | --- |
| Seguridad | Con dos médicos, un investigador, un administrador y una sesión anónima, use pytest y un cliente HTTP para probar acceso propio, ajeno, cruzado y anónimo sobre rutas del inventario. Pruebe contraseña inválida, cuenta inactiva, cinco fallos en ventana, JWT previo revocado y configuración sin clave personalizada fuera de desarrollo. Compruebe HTTPS, disponibilidad de puertos y tratamiento de campos libres con datos ficticios. | Matriz por credencial y ruta, códigos, eventos y hallazgos sin secretos. |
| Resiliencia | Interrumpa el worker de prueba tras reclamar un análisis. Verifique retorno a cola tras el límite y fallo al agotar intentos. Ejecute respaldo y restauración coordinada en otro entorno. | Cronología, estados, hashes, RPO y RTO. |
| STOW-RS | Envíe un DICOM válido, carga multipart, una mezcla válida e inválida y una solicitud sin autorización al sistema de prueba. Compare el cuerpo de respuesta con las imágenes y banderas persistidas. | Resultado HTTP, reconciliación por instancia y verificación de eliminación de etiquetas. |
| FHIR | Descargue un análisis terminado. Valide JSON con HL7 FHIR Validator para R4 y el perfil acordado. Compruebe referencias, versión, ausencia de identificadores directos y manejo de análisis ajenos o incompletos. | Informe de validación e importación en HCE de ensayo. |
| Usabilidad | Aplique el [protocolo SUS](08-usabilidad-sus.md) a 5–10 médicos o residentes con tareas, observación y consentimiento. | Hoja codificada, tasas, tiempos y puntuaciones. |

## Criterios de salida

- Todas las suites obligatorias pasan en la revisión candidata. Cada requisito M aplicable al piloto tiene evidencia y las pruebas de autorización y desidentificación pasan al 100 %.
- Los defectos con exposición de datos, pérdida de trazabilidad, corrupción o ruptura del ciego se resuelven antes del piloto. Los casos bloqueados se registran con el motivo y no cuentan como aprobados.
- Para declarar listo cada intercambio I4 se cumple su prueba local y la prueba en los sistemas institucionales de ensayo. El piloto de doble lectura requiere un ensayo del ciego entre lectores y frente a la salida del modelo.
- Se alcanzan los umbrales de desempeño, restauración y usabilidad del perfil acordado o se documenta la decisión de postergar el piloto y repetir las pruebas.

## Plantilla de informe

| Campo | Registro |
| --- | --- |
| Fecha, responsable, revisión y entorno | |
| Dependencias, motor, cantidad de workers | |
| Datos de prueba y huella del bundle | |
| Versiones de contrato, navegador y perfil de carga | |
| Total, aprobadas, fallidas, bloqueadas | |
| Decisión de salida, responsable y fecha | |

| ID de caso / RF o RNF | Esperado | Observado | Estado (verificada, fallida, bloqueada) | Evidencia o incidencia | Reprueba |
| --- | --- | --- | --- | --- | --- |
| | | | | | |
