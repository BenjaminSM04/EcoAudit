# EcoAudit · Propuesta de piloto para direcciones médicas

## 1. Propósito y alcance

La variación de equipos, parámetros de adquisición y poblaciones entre centros puede afectar a un modelo de clasificación de ecografías mamarias. La evaluación local requiere conocer qué imágenes se analizaron, qué versión del modelo produjo el resultado, cuándo se abstuvo y cómo se compara la salida con lecturas independientes. EcoAudit es un prototipo de investigación desarrollado como proyecto de grado de Ingeniería de Sistemas en Bolivia para documentar ese proceso.

**Qué hace.** Organiza imágenes en casos seudonimizados, reconstruye archivos de imagen sin metadatos de origen, muestra banderas de calidad y aplica un modelo versionado a la imagen o al ROI revisado por la persona usuaria. Presenta una probabilidad calibrada, avisos, abstención, alerta de cambio de dominio cuando está disponible y mapa de activación. El investigador puede agrupar casos etiquetados en cohortes y revisar discriminación y calibración por paciente. La iteración 4 incorpora lectura BI-RADS independiente, indicadores, comparación de versiones, consulta de bitácora y conexiones DICOMweb y FHIR para ensayo.

**Límites de uso.** EcoAudit no es un dispositivo médico. No emite un diagnóstico, no indica biopsias o tratamientos y no dirige la priorización ni la atención clínica. Una probabilidad o región resaltada es una salida experimental. La evidencia de desarrollo descrita en el manuscrito no sustituye una validación externa. El hospital mantiene su flujo asistencial y su expediente en los sistemas institucionales.

## 2. Operación e integración

| Aspecto | Condición para el piloto |
| --- | --- |
| Infraestructura | Servidor o máquina virtual institucional con CPU, Docker Compose, PostgreSQL y almacenamiento persistente para imágenes, mapas y modelos, con respaldo. Dimensionar CPU, memoria y disco con el ensayo de carga y el volumen aprobado. Las estaciones requieren navegador y acceso a la red autorizada. |
| Acceso | Credenciales individuales para médicos, investigadores y administradores. Acceso HTTPS desde los equipos autorizados, con base y servicios internos privados. |
| Recepción PACS | DICOMweb STOW-RS de I4 por cuenta autorizada, desde una pasarela o PACS de ensayo. Validar sintaxis DICOM, protección de píxeles y conciliación de respuestas antes de habilitar el flujo. |
| Salida HCE | Descarga FHIR R4 por análisis terminado. Validar versión, referencias y advertencia de investigación. Ensayar el perfil receptor en una HCE de pruebas y designar responsable de custodia de los archivos. |
| Datos y seguridad | Usar seudónimos, verificar texto visible antes de cargar, custodiar por separado la correspondencia y limitar accesos según rol, ámbito y protocolo. Revisar bitácora y efecto de exportaciones, ensayar restauración y documentar retención y respuesta a incidentes. |

La institución designaría un responsable clínico, un coordinador de investigación y un responsable técnico. Participan el custodio de datos y el comité de ética competente. La universidad aportaría el protocolo, la versión de software y modelo, la guía de operación y el informe de cierre.

## 3. Piloto de validación con aval ético

1. **Acuerdo y protocolo.** Definir población, fuentes autorizadas, tamaño muestral, unidad paciente/lesión y reglas de selección, atribución de referencias y análisis. Congelar el modelo, los umbrales y las reglas para pares incompletos, lecturas expuestas y archivos fuera de dominio. Obtener aval ético y autorización de la institución antes de acceder a datos de pacientes.
2. **Ensayo técnico.** Usar imágenes ficticias para verificar roles, respaldo, recepción STOW-RS, exportación FHIR, latencia y aislamiento. Ensayar el ciego con dos lectores autorizados y verificar que sus recorridos impidan ver las otras lecturas y el resultado algorítmico. Resolver las deficiencias de acceso o exposición antes de iniciar la recogida.
3. **Evaluación observacional.** Usar un conjunto autorizado e independiente conforme al protocolo. Registrar primero las dos valoraciones y mantener las salidas del modelo fuera del recorrido de lectura. Ejecutar el SUS con 5–10 médicos o residentes. Conservar procedencia del modelo, denominadores y causas de exclusión.
4. **Análisis y cierre.** Presentar indicadores con tamaños de muestra, incertidumbre y limitaciones. Entregar un informe al hospital y al comité conforme al protocolo. Documentar custodia o eliminación de copias y la decisión de cierre o de una fase de investigación posterior.

| Indicador | Cálculo y lectura |
| --- | --- |
| Concordancia interlector | Kappa de Cohen, `(pₒ − pₑ)/(1 − pₑ)`, para dos lectores sobre unidades con pares completos y categorías fijadas en el protocolo. Informar n, acuerdo bruto, matriz e intervalo de confianza. Calcularlo en el análisis del piloto. El kappa del panel contrasta lectura y modelo con categorías dicotomizadas. |
| Tasa de abstención | Análisis indeterminados o fuera de dominio / análisis terminados. Informar también cada componente. El campo `abstention_rate` del panel visible cuenta solo indeterminados. |
| Alertas de dominio | Alertas / análisis con monitorización disponible. Adjuntar cobertura de monitorización. El panel usa como denominador los terminados y devuelve por separado el número monitorizado. |
| Usabilidad | SUS de 0–100 con n, mediana y dispersión, más porcentaje de tareas sin ayuda y dificultades observadas. |
| Latencia | p95 en segundos por versión, para servicio y tiempo total de cola y procesamiento. Registrar tamaño de muestra, carga y fallos. |

La decisión solicitada a Dirección Médica es autorizar la **preparación** del piloto, designar a sus responsables y acordar el entorno de ensayo y la ruta de revisión ética. La incorporación de datos de pacientes queda condicionada al aval y a la verificación operativa. [Plan de pruebas](06-plan-de-pruebas.md) · [Marco legal y ético](11-marco-legal-y-etico.md)
