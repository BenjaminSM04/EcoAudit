# Requisitos de EcoAudit

## Actores

| Actor | Responsabilidad y alcance |
| --- | --- |
| Médico (`medico`) | Crea y consulta sus casos, carga imágenes, selecciona el ROI y solicita análisis. Participa en la lectura ciega en I4. |
| Investigador (`investigador`) | Gestiona sus casos y cohortes, consolida etiquetas de referencia y evalúa resultados. |
| Administrador (`admin`) | Accede a casos y cohortes de todas las cuentas, gestiona usuarios y activa versiones. Consulta la bitácora en I4. |
| Operador técnico | Instala, migra, respalda y registra paquetes mediante CLI. Es una responsabilidad de operación. |
| PACS o pasarela DICOMweb (I4) | Remite instancias de prueba mediante STOW-RS como cliente autorizado. |
| Integrador de HCE (I4) | Obtiene y valida la exportación FHIR R4 en un entorno de prueba, bajo autorización institucional. |

MoSCoW: **M** imprescindible para el alcance asignado, **S** importante, **C** deseable, **W** fuera del alcance actual. **I4** identifica criterios por comprobar al integrar. Los umbrales de evaluación son propuestas del proyecto.

## Requisitos funcionales

| ID | Requisito | Prioridad | Criterio de aceptación |
| --- | --- | --- | --- |
| RF-01 | Iniciar sesión y recuperar identidad y rol. | M | Un usuario activo válido recibe un JWT y `GET /api/auth/me` identifica la cuenta. Una contraseña errónea o cuenta inactiva rechaza el ingreso. |
| RF-02 | Crear, listar y consultar casos seudonimizados. | M | Un alta válida devuelve `201`. La cuenta recupera el caso, otra cuenta no administradora recibe `404` y administración puede consultarlo. |
| RF-03 | Cargar imágenes válidas, reconstruir PNG y señalar calidad y duplicados. | M | Cargar DICOM sin compresión con etiquetas ficticias y recuperar PNG sin esas etiquetas. Cargar otra copia de la imagen con el mismo usuario y comprobar el aviso. Un archivo no decodificable se rechaza. |
| RF-04 | Seleccionar ROI manual o sugerido y conservarlo al analizar. | S | El ROI válido se conserva en píxeles de origen. Se rechaza uno fuera de límites o menor a 8 px por lado. Una sugerencia del localizador instalado puede ser reemplazada por el usuario. |
| RF-05 | Encolar y resolver análisis con la versión activa en la solicitud. | M | Una solicitud válida devuelve `202`. El worker persiste resultado calibrado, decisión, avisos y CAM. Cambiar el modelo activo entre solicitud y ejecución conserva la referencia original. |
| RF-06 | Descargar PDF del análisis terminado. | S | El archivo abre y contiene el identificador y la versión, un análisis sin resultado devuelve `409` y uno ajeno `404` para una cuenta ordinaria. |
| RF-07 | Auditar cohortes desde análisis existentes o desde un lote. | M | Ambos orígenes generan una cohorte persistente con métricas por paciente y exportación PDF/CSV. Un lote inválido deja la base y archivos sin altas parciales. |
| RF-08 | Registrar paquetes y activar versiones de modelo. | M | La CLI rechaza una cabeza incompatible. Una versión válida se identifica por SHA-256. Solo el administrador puede activar por API. |
| RF-09 | Administrar usuarios y restablecer contraseñas. | M | Un administrador crea, cambia rol o estado y restablece credenciales. Una cuenta ordinaria se rechaza y el administrador no puede desactivarse ni quitarse su rol. |
| RF-10 | Cambiar la contraseña propia. | M | La operación exige la contraseña vigente y la nueva de al menos diez caracteres. La sesión anterior pierde validez y se puede iniciar otra. |
| RF-11 | Consultar indicadores de actividad, rendimiento y concordancia. I4. | S | Los tres endpoints de `/api/stats` devuelven agregados reproducibles sobre una fixture conocida y respetan el ámbito autorizado. El calendario incluye días sin actividad y los agregados sin muestra usan valores nulos donde corresponda. |
| RF-12 | Registrar dos lecturas BI-RADS independientes y ciegas. I4. | M | Con dos cuentas lectoras, cada valoración se guarda con autoría. Antes del cierre del ciego, el lector no recibe la otra valoración ni la salida del modelo por los canales bajo evaluación. El kappa sobre pares completos coincide con un cálculo independiente. |
| RF-13 | Exportar resultados mediante HL7 FHIR R4. I4. | S | Un resultado terminado y autorizado se exporta por `/api/analyses/{id}/fhir`. Un validador R4 acepta la muestra y las referencias, la versión y el carácter experimental pueden comprobarse. |
| RF-14 | Recibir estudios por DICOMweb STOW-RS. I4. | S | Remitir un estudio ficticio por `POST /api/dicomweb/studies`, reconciliar la respuesta con las imágenes persistidas y verificar descarte de metadatos. Probar entradas inválidas y solicitudes sin autorización. |
| RF-15 | Consultar la bitácora desde la administración. I4. | S | Un administrador recupera eventos conocidos con fecha, acción y actor cuando exista. Las otras cuentas no acceden a la consulta. |
| RF-16 | Comparar versiones sobre una cohorte común. I4. | S | Dos versiones identificables se evalúan con las mismas imágenes, pacientes y etiquetas. La salida permite verificar denominadores y resultados pareados, con tratamiento explícito de fallos. |
| RF-17 | Escribir resultados en la HCE asistencial. Fuera del alcance del prototipo. | W | El piloto se ejecuta en un entorno aislado y solo se prueba la importación en una HCE de ensayo. |

## Requisitos no funcionales

Se emplean los nombres de características de la edición 2011 para las siete categorías solicitadas. El [modelo de medición](07-evaluacion-iso25010.md) identifica las subcaracterísticas y su relación con la revisión del estándar.

| ID | Característica | Requisito | Prioridad | Criterio de aceptación |
| --- | --- | --- | --- | --- |
| RNF-01 | Seguridad | Autorización uniforme por rol y recurso. | M | El 100 % de los accesos indebidos de la matriz API se deniega, incluyendo imágenes, CAM y descargas. |
| RNF-02 | Seguridad | Minimizar datos personales de pacientes. | M | En el 100 % de las muestras de prueba se descartan EXIF y etiquetas DICOM. El operador verifica y excluye texto identificable incrustado antes de cargar. |
| RNF-03 | Seguridad | Proteger credenciales y registrar acciones. | M | La base conserva hashes de contraseña. El sexto intento en la ventana de 15 min tras cinco fallos devuelve `429` y el cambio o restablecimiento invalida JWT anteriores. Se comprueban los eventos previstos. |
| RNF-04 | Fiabilidad | Recuperar trabajos interrumpidos y preservar consistencia del lote. | M | Un `running` vencido vuelve a `pending` con intentos disponibles o queda `failed` al agotar tres reclamaciones. Una falla de escritura del lote revierte sus altas. |
| RNF-05 | Eficiencia de desempeño | Medir espera e inferencia con carga acotada. | S | Con el perfil del plan, p95 de servicio del análisis ≤ 5 s, p95 extremo a extremo ≤ 15 s y tasa de fallos ≤ 1 %. |
| RNF-06 | Usabilidad | Permitir completar tareas y reconocer los límites del resultado. | S | Al menos 80 % de las tareas elegibles se completa sin ayuda y la media SUS es ≥ 70. Nadie interpreta una abstención como diagnóstico. |
| RNF-07 | Mantenibilidad | Aplicar migraciones repetibles y sostener regresiones automatizadas. | M | Una base vacía y una heredada soportada alcanzan la revisión esperada. Una segunda ejecución no introduce cambios. Pasan las verificaciones automáticas del plan. |
| RNF-08 | Compatibilidad | Intercambiar imágenes y datos con sistemas de prueba por STOW-RS y FHIR R4. I4. | S | Pasa el 100 % de los escenarios obligatorios de interoperabilidad acordados con PACS/HCE y se identifica el perfil de intercambio aceptado. |
| RNF-09 | Portabilidad | Instalar en desarrollo y en Docker. | M | SQLite local y PostgreSQL en Compose superan el mismo humo de migración, ingreso, carga y análisis con un paquete de demostración. |
| RNF-10 | Fiabilidad | Recuperar base y archivos como un conjunto coherente. | S | Un ensayo restaura casos, versiones, imágenes y CAM con sus referencias y hashes. RPO ≤ 24 h y RTO ≤ 2 h para el entorno de piloto propuesto. |
| RNF-11 | Seguridad | Servir el piloto por HTTPS con credenciales de entorno. | M | Un escaneo del entorno confirma HTTPS válido y una única entrada web publicada. API, worker y base usan red privada, y el arranque fuera de desarrollo rechaza la clave predeterminada. |
| RNF-12 | Mantenibilidad | Reproducir la procedencia de un análisis. | M | Cada resultado auditado permite recuperar el identificador, la ficha y la huella del paquete asociado tras una activación posterior. |
