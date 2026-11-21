# Matriz de trazabilidad

Los nombres abreviados de Python corresponden a `backend/tests/`. Los de Playwright corresponden a `e2e/tests/`. Los casos citados acreditan cobertura inspeccionada. Los pasos complementarios cubren criterios que requieren comprobación adicional. En I4 se indican los seis nombres solicitados y, donde difieren, los archivos reales observados en el corte.

| ID | Componente o archivo | Prueba automática y alcance | Verificación complementaria |
| --- | --- | --- | --- |
| RF-01 | `backend/app/routers/auth.py`, `deps.py`, `frontend/src/auth.tsx` | `test_api.py` (credenciales e inactividad), `login.spec.ts` | Verificar perfil y vigencia del JWT en la instancia. |
| RF-02 | `backend/app/routers/cases.py`, `frontend/src/pages/CasesPage.tsx` | `test_api.py`, `aislamiento.spec.ts`, `medico.spec.ts` | Revisar el alta con notas ficticias. |
| RF-03 | `backend/app/services.py`, `pipeline/imaging.py` y `pipeline/quality.py` bajo `backend/app/` | `test_pipeline.py`, `test_duplicates.py`, `test_api.py`, `medico.spec.ts` | DICOM de prueba y revisión visual de texto en píxeles. |
| RF-04 | `backend/app/pipeline/localizer.py` y `runner.py`, `routers/cases.py`, `frontend/src/components/ImageWorkspace.tsx` | `test_pipeline.py`, `test_api.py`, `medico.spec.ts` (ROI manual) | Con/sin localizador, revisar sugerencia y reemplazo. |
| RF-05 | `backend/app/routers/cases.py`, `worker.py` y `pipeline/runner.py` | `test_api.py`, `test_pipeline.py`, `test_requeue.py`, `test_inline_drain.py`, `medico.spec.ts` | Cambiar versión activa con un análisis pendiente y comprobar el vínculo. |
| RF-06 | `backend/app/routers/cases.py` y `reports.py`, `frontend/src/components/ImageWorkspace.tsx` | `medico.spec.ts` comprueba descarga, identificador y firma PDF | Abrir, verificar contenido y comprobar códigos `404` y `409` directamente. |
| RF-07 | `backend/app/routers/cohorts.py` y `cohorts.py`, `frontend/src/pages/AuditPage.tsx` y `CohortDetailPage.tsx` | `test_cohorts.py`, `test_cohort_analyses.py`, `test_cohort_batch.py`, `auditoria.spec.ts` | Cotejar métricas y denominadores con cálculo de referencia. |
| RF-08 | `backend/app/cli.py`, `registry.py`, `routers/model_registry.py` y `pipeline/bundle.py`, `frontend/src/pages/ModelsPage.tsx` | `test_pipeline.py`, `test_api.py`, `admin.spec.ts` | Registrar dos paquetes por CLI; cotejar hash y activación. |
| RF-09 | `backend/app/routers/users.py`, `frontend/src/pages/UsersPage.tsx` | `test_api.py`, `test_account.py`, `admin.spec.ts` | Cotejar cada cambio con la respuesta y el evento. |
| RF-10 | `backend/app/routers/auth.py`, `deps.py`, `frontend/src/pages/AccountPage.tsx` | `test_account.py`, `cuenta.spec.ts` | Comprobar revocación con el token anterior. |
| RF-11 | `backend/app/routers/stats.py` | I4 `test_hospital.py`. Visible en `test_hospital.py`. | Revisar fechas UTC y valores vacíos sin sustituirlos por cero. |
| RF-12 | `backend/app/routers/cases.py`, `models.py`, `schemas.py`, `routers/stats.py`, migración `0002_lecturas_clinicas.py` | I4 `test_hospital.py` y `test_hospital.py`. Visible en `test_hospital.py`. | Validar acceso de dos lectores, exposición por API/visores/informes y cálculo humano–humano del piloto. |
| RF-13 | `backend/app/routers/cases.py` y `fhir.py` | I4 `test_hospital.py`. Visible en `test_hospital.py`. | Validar R4 y perfil receptor con una HCE de ensayo. |
| RF-14 | `backend/app/routers/dicomweb.py` y `services.py` | `test_dicomweb.py` (I4, formatos, errores y almacenamiento) | Reconciliar el PACS/pasarela con el JSON devuelto. |
| RF-15 | `backend/app/routers/audit_log.py`, `deps.py` y `models.py` | I4 `test_hospital.py`. Visible en `test_hospital.py`. | Contrastar conteos, paginación y evento de exportación. |
| RF-16 | `backend/app/routers/cohorts.py`, `cohorts.py` y `worker.py` | I4 `test_hospital.py`. Visible en `test_cohort_analyses.py`. | Confrontar denominadores e inclusión de fallos con dos versiones y una cohorte de prueba. |
| RF-17 | Entorno del piloto, `docker-compose.yml` y exportación FHIR | `test_hospital.py` (I4, descarga; cobertura parcial) | Verificar aislamiento de la HCE asistencial en el ensayo. |
| RNF-01 | `backend/app/deps.py` y `routers/` | `test_api.py`, `test_cohort_analyses.py`, `test_cohort_batch.py`, `aislamiento.spec.ts`, `admin.spec.ts`; `test_hospital.py` y `test_hospital.py` (I4) | Completar matriz API de permisos con CAM, descargas y rutas nuevas. |
| RNF-02 | `backend/app/pipeline/imaging.py` y `services.py` | `test_pipeline.py`, `test_cohort_batch.py`; `test_dicomweb.py` (I4) | Inspeccionar imágenes por texto incrustado y revisar campos libres. |
| RNF-03 | `backend/app/security.py`, `deps.py`, `routers/auth.py` y `routers/users.py` | `test_account.py`, `test_api.py`, `cuenta.spec.ts` | Comprobar la política de auditoría y el hash en una base de ensayo. |
| RNF-04 | `backend/app/worker.py`, `routers/cohorts.py` y `storage.py` | `test_requeue.py`, `test_inline_drain.py`, `test_api.py`, `test_cohort_batch.py` | Simular interrupción con Compose y revisar recuperación. |
| RNF-05 | `backend/app/worker.py`, `models.py`, `routers/stats.py` | `test_hospital.py` (I4, agregación, cobertura parcial), `test_api.py` (funcionamiento) | Ejecutar campaña de carga. |
| RNF-06 | `frontend/src/pages/CaseDetailPage.tsx` y `components/ResultPanel.tsx` | `medico.spec.ts`, `login.spec.ts` (funcionamiento) | Aplicar observación por tareas y SUS. |
| RNF-07 | `backend/app/migrate.py`, `backend/migrations/`, `.github/workflows/ci.yml` | `test_migrations.py` y suites de CI | Probar actualización sobre copia de datos anterior a I4. |
| RNF-08 | `backend/app/routers/dicomweb.py`, `routers/cases.py` y `fhir.py` | `test_dicomweb.py` y `test_hospital.py` (I4) | Ejecutar prueba de conformidad con sistemas receptores y emisores. |
| RNF-09 | `backend/app/config.py`, `backend/Dockerfile`, `docker-compose.yml` | `test_migrations.py`, `medico.spec.ts` (base de desarrollo) | Humo Compose/PostgreSQL por separado. |
| RNF-10 | `docker-compose.yml`, `backend/app/storage.py` | Sin prueba automática específica en el corte. | Ensayo de restauración coordinada, RPO y RTO. |
| RNF-11 | `backend/app/config.py`, `frontend/nginx.conf`, `docker-compose.yml` | Sin prueba automática específica del proxy TLS en el corte. | Verificar clave de entorno y escanear el punto HTTPS y red publicada. |
| RNF-12 | `backend/app/registry.py`, `models.py`, `routers/cases.py` | `test_pipeline.py`, `test_api.py`, `medico.spec.ts` (cobertura parcial) | Cotejar ficha y SHA-256 después de activar un paquete distinto. |
