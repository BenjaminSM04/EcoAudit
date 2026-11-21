# Evaluación de calidad del producto según ISO/IEC 25010

Se conserva la nomenclatura solicitada de 2011, edición retirada y sustituida. La revisión de 2023 amplía el modelo y emplea, entre otras, capacidad de interacción y flexibilidad para aspectos relacionados con usabilidad y portabilidad. Se seleccionan siete características para el proyecto. La adecuación funcional se evalúa mediante los RF y la trazabilidad. Los umbrales son criterios internos propuestos para el perfil de ensayo, sin pretensión de certificación. [ISO/IEC 25010:2011](https://www.iso.org/standard/35733.html/) · [ISO/IEC 25010:2023](https://www.iso.org/standard/78176.html)

## Métricas e instrumentos

| ID / RNF | Característica y subcaracterística | Fórmula y obtención en EcoAudit | Umbral | Instrumento |
| --- | --- | --- | --- | --- |
| M01 / RNF-01 | Seguridad · confidencialidad | 100 × accesos indebidos denegados / intentos indebidos planificados. Incluir rutas de casos, archivos, análisis y exportaciones. | 100 % | Matriz HTTP y pytest |
| M02 / RNF-02 | Seguridad · confidencialidad | 100 × muestras reconstruidas sin metadatos de origen y sin texto identificable / muestras inspeccionadas. Registrar si la muestra se excluyó en origen. | 100 % de muestras admitidas | pydicom, Pillow y revisión de píxeles |
| M03 / RNF-03 | Seguridad · responsabilidad | 100 × acciones de prueba con evento consistente / acciones que deben registrarse. Comprobar actor, entidad y fecha. | 100 % | Consulta de `audit_log` y API administrativa I4 |
| M04 / RNF-04 | Fiabilidad · tolerancia a fallos | 100 × escenarios de interrupción y escritura que terminan en el estado esperado / escenarios ensayados. | 100 % | Logs, estado de `analyses` y prueba de lote |
| M05 / RNF-05 | Eficiencia de desempeño · comportamiento temporal | p95 por modelo de `finished_at − started_at` en s, sobre análisis `done` con ambas marcas. En `GET /api/stats/performance` se obtiene de `models[].latency_seconds.processing.p95` y se conserva `n`. | ≤ 5 s | Endpoint I4 y contraste SQL |
| M06 / RNF-05 | Eficiencia de desempeño · comportamiento temporal | p95 de `finished_at − created_at` en s en los análisis `done`. Consultar `models[].latency_seconds.total.p95` para medir espera y procesamiento. | ≤ 15 s | Endpoint I4, cliente de carga y SQL |
| M07 / RNF-05, RNF-04 | Eficiencia de desempeño · capacidad bajo el perfil definido; fiabilidad · madurez | 100 × intentos fallidos o vencidos / intentos del perfil. Cada intento se contabiliza una vez. | ≤ 1 % | Cliente de carga y estados persistidos |
| M08 / RNF-06 | Usabilidad · operabilidad y protección frente a errores | 100 × tareas completadas sin ayuda / tareas elegibles. Contar interpretaciones de abstención como diagnóstico. | ≥ 80 % y cero interpretaciones erróneas de ese tipo | Observación estructurada |
| M09 / RNF-06 | Usabilidad · operabilidad percibida | Promedio de los puntajes SUS individuales completos, con fórmula del protocolo. | ≥ 70/100 | Cuestionario SUS |
| M10 / RNF-07 | Mantenibilidad · capacidad de prueba y modificación | 100 × escenarios de migración aprobados / escenarios definidos. Repetir en base vacía y heredada soportada y ejecutar regresiones. | 100 % | Alembic, pytest y CI |
| M11 / RNF-08 | Compatibilidad · interoperabilidad | 100 × escenarios de intercambio conformes / escenarios obligatorios acordados. Verificar validación de FHIR y reconciliación STOW-RS. | 100 % | Validador R4 y PACS/HCE de ensayo |
| M12 / RNF-09 | Portabilidad · instalabilidad | Perfiles con instalación y humo superado / perfiles previstos. | 2/2 | SQLite local y Compose/PostgreSQL |
| M13 / RNF-10 | Fiabilidad · capacidad de recuperación | RPO = intervalo entre el último estado recuperado y la interrupción simulada. RTO = duración desde la declaración del incidente hasta el humo satisfactorio. Cotejar archivos y hashes. | RPO ≤ 24 h, RTO ≤ 2 h, referencias completas | Registro de respaldo y restauración |
| M14 / RNF-11 | Seguridad · confidencialidad en tránsito | Entradas web del piloto con TLS válido / entradas publicadas. Verificar aislamiento de servicios internos y rechazo de la clave predeterminada fuera de desarrollo. | 1/1 y controles verificados | Cliente TLS, inspección de red y arranque controlado |
| M15 / RNF-12 | Mantenibilidad · capacidad de análisis | 100 × resultados con identificación y huella verificables tras activar otro modelo / resultados auditados. | 100 % | API, informe PDF, BD y hash del paquete |

Ejecute el [plan](06-plan-de-pruebas.md). Use una base o ámbito exclusivamente de ensayo al consumir `performance`, que agrupa análisis terminados por modelo. Si faltan observaciones, conserve el agregado nulo y marque el criterio como pendiente de medición. Un ensayo de latencia y un SUS pequeño no estiman el desempeño diagnóstico.

## Registro de resultados

| Métrica | Valor | n o cobertura | Revisión / entorno | Fecha | Estado | Evidencia |
| --- | --- | --- | --- | --- | --- | --- |
| M01 | | | | | | |
| M02 | | | | | | |
| M03 | | | | | | |
| M04 | | | | | | |
| M05 | | | | | | |
| M06 | | | | | | |
| M07 | | | | | | |
| M08 | | | | | | |
| M09 | | | | | | |
| M10 | | | | | | |
| M11 | | | | | | |
| M12 | | | | | | |
| M13 | | | | | | |
| M14 | | | | | | |
| M15 | | | | | | |
