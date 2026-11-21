# Metodología Scrum adaptada a un desarrollador

El objetivo de producto es construir una plataforma reproducible para cargar, analizar y auditar ecografías mamarias en investigación y hacer explícitas la procedencia del modelo y las limitaciones de generalización.

## Responsabilidades, artefactos e inspección

| Elemento | Aplicación al proyecto |
| --- | --- |
| Product Owner | El tesista prioriza resultados de ingeniería y requisitos científicos. El tutor y los referentes clínicos pueden aportar criterios y revisar entregables. |
| Scrum Master | El tesista facilita la inspección del trabajo y gestiona impedimentos. La revisión con el tutor permite recibir observaciones externas. |
| Developer | El tesista implementa, prueba y documenta los incrementos. |
| Product Backlog | Requisitos RF/RNF, hoja de ruta, riesgos, historias y criterios de aceptación. El objetivo de producto orienta el orden. |
| Sprint Backlog | Objetivo del sprint, historias seleccionadas y plan técnico con tareas y evidencias esperadas. |
| Incremento | Versión utilizable en entorno de prueba que cumple la definición de terminado. |
| Eventos adaptados | En planificación se selecciona un objetivo. Durante el sprint se revisa diariamente el avance mediante notas breves. La revisión usa una demostración y la retrospectiva identifica un cambio de proceso para el siguiente ciclo. |

La adaptación concentra responsabilidades en una persona. Los puntos son estimaciones relativas retrospectivas, en escala 1, 2, 3, 5, 8, 13. El historial no permite reconstruir velocidad, fechas de inicio ni actas. [Guía de Scrum 2020](https://scrumguides.org/docs/scrumguide/v2020/2020-Scrum-Guide-Spanish-European.pdf)

**Definición de terminado.** El cambio se recorre por su entrada normal con datos ficticios. Los tests y el análisis estático aplicables pasan y la evidencia queda asociada a la revisión. Se verifica autorización y tratamiento de datos en rutas nuevas. Los cambios de persistencia incluyen migración ensayada. Se actualizan documentación, contrato y trazabilidad. Los cambios de modelo llevan ficha, huella y límites. Una historia clínica o de interoperabilidad requiere además la verificación prevista en su aceptación antes de declararse concluida.

## Reconstrucción de sprints

La numeración conserva la iteración 0, la segunda y la tercera de la [hoja de ruta](../roadmap.md) y asigna el sprint 4 al incremento de API hospitalaria. El sprint 1 es una desagregación analítica del trabajo de inferencia y versionado incluido en el commit inicial. El historial se obtuvo con `git log --format="%ad %s" --date=short`. La línea base lleva fecha 2026-11-19 y el incremento de backend I4 se incorporó el 2026-11-21.

| Sprint | Objetivo | Evidencia |
| --- | --- | --- |
| 0 | Construir el flujo base de acceso y captura. | `fb806bd` «Versión inicial de EcoAudit». `b7e957b` «Normaliza fines de línea y marca binarios en .gitattributes» es mantenimiento transversal. |
| 1 | Fijar el contrato del pipeline y su procedencia. | `fb806bd`, ADR 0001, 0002 y 0004, exportador y contrato del bundle. Sin commit exclusivo. |
| 2 | Incorporar auditoría inicial, informes y ROI experimental. | «Segunda iteración» de la hoja de ruta y artefactos ya incluidos en `fb806bd`, como `ml/ecoaudit_ml/compare_roi.py` y la guía de tesis. |
| 3 | Persistir cohortes, endurecer cuentas y automatizar verificación. | `027ca58` «Cohortes persistentes, lotes de imágenes y robustez de cuentas», `be0993d` «Migraciones con Alembic y procesamiento de la cola al arrancar», `335d8c2` «Pruebas de extremo a extremo con Playwright». Los últimos dos materializan pendientes de la hoja de ruta. |
| 4 | Integrar lectura independiente, indicadores y conexiones de ensayo. | `8a86fe7` «API hospitalaria: indicadores, lectura clínica ciega, FHIR, DICOMweb, bitácora y comparación de modelos». Las pantallas nuevas y el protocolo de doble lectura quedan sujetos a verificación. |

| Sprint / historia | Historia de usuario | Criterio de aceptación | Puntos |
| --- | --- | --- | --- |
| 0 / HU-01 | Como médico, quiero ingresar y crear casos seudonimizados para revisar mis imágenes. | Ingreso válido y alta de caso; otra cuenta ordinaria recibe `404`. RF-01/02. | 5 |
| 0 / HU-02 | Como médico, quiero cargar ecografías y ver banderas para revisar la calidad de los archivos. | PNG reconstruido sin metadatos y aviso al repetir la imagen. RF-03. | 5 |
| 0 / HU-03 | Como administrador, quiero gestionar cuentas para asignar permisos. | Alta, cambios de rol y estado solo con permiso. RF-09. | 3 |
| 1 / HU-04 | Como médico, quiero analizar una imagen o un ROI para inspeccionar la salida experimental. | La cola termina y el visor presenta probabilidad, decisión, advertencias y CAM. RF-04/05. | 8 |
| 1 / HU-05 | Como operador, quiero registrar paquetes identificados para reproducir el modelo de cada análisis. | La ficha y la cabeza se validan y una activación posterior conserva versiones históricas. RF-08/RNF-12. | 5 |
| 2 / HU-06 | Como investigador, quiero importar etiquetas para medir discriminación y calibración por paciente. | CSV con dos clases genera AUROC y métricas de calibración. RF-07. | 5 |
| 2 / HU-07 | Como médico, quiero revisar una propuesta de ROI y descargar el informe para reproducir la selección y el resultado. | Puede reemplazarse la caja, y el PDF terminado muestra la región y la versión. RF-04/06. | 5 |
| 3 / HU-08 | Como investigador, quiero procesar un lote con manifiesto para auditar una cohorte persistente. | Progreso observable, PDF y CSV. Un lote inválido no deja altas parciales. RF-07. | 8 |
| 3 / HU-09 | Como usuario, quiero cambiar mi contraseña para revocar sesiones anteriores. | Se revocan tokens anteriores y se limita el ingreso tras cinco fallos. RF-10/RNF-03. | 5 |
| 3 / HU-10 | Como operador, quiero migraciones y recuperación de cola para desplegar actualizaciones reproducibles. | Segunda migración sin cambios; recuperación y límite de intentos comprobados. RNF-04/07. | 8 |
| 3 / HU-11 | Como tesista, quiero recorridos Playwright para detectar regresiones de interfaz. | Chromium recorre ingreso, casos, auditoría, cuenta y administración en entorno aislado. RNF-06/07. | 5 |
| 4 / HU-12 | Como médico, quiero registrar una categoría de forma independiente para estudiar acuerdo. | Dos lectores autorizados completan la tarea bajo ciego verificado; se registra un valor por lector y análisis. RF-12. | 8 |
| 4 / HU-13 | Como investigador, quiero ver indicadores y comparar versiones para investigar diferencias sobre los mismos datos. | Indicadores con denominador y comparación pareada con dos versiones identificables. RF-11/16. | 8 |
| 4 / HU-14 | Como integrador, quiero recibir imágenes y exportar resultados estructurados para ensayar PACS y HCE. | STOW-RS se reconcilia con imágenes persistidas y el JSON valida en R4 bajo el perfil acordado. RF-13/14/RNF-08. | 8 |
| 4 / HU-15 | Como administrador, quiero consultar eventos para reproducir acciones relevantes. | La bitácora devuelve los eventos esperados y rechaza a otros roles. RF-15. | 3 |

Las historias de I4 se evalúan con los [criterios de salida](06-plan-de-pruebas.md). La validación externa, el piloto institucional y el SUS en participantes quedan sujetos a su ejecución y evidencias.
