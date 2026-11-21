# Marco legal y ético en Bolivia

EcoAudit se presenta como prototipo de investigación, sin uso asistencial autorizado en este proyecto. El uso previsto, los flujos de datos y los destinatarios deben quedar descritos en el protocolo y en los acuerdos institucionales. La universidad y el hospital deben verificar el alcance normativo aplicable y las condiciones de tratamiento antes de emplear datos de pacientes.

## Constitución Política del Estado

El artículo 21, numeral 2, reconoce los derechos a la privacidad, intimidad, honra, honor, propia imagen y dignidad. El artículo 130 prevé la Acción de Protección de Privacidad para las situaciones que describe, incluyendo impedimentos indebidos o ilegales para conocer, objetar, eliminar o rectificar datos registrados. El hospital debe designar un responsable y un canal para tramitar solicitudes y documentar las decisiones sobre datos, archivos derivados y respaldos. [Constitución Política del Estado · Gaceta Oficial](https://www.gacetaoficialdebolivia.gob.bo/app/webroot/archivos/constitucion.pdf)

EcoAudit aplica acceso por rol y propietario. La reconstrucción de PNG descarta metadatos DICOM y EXIF. El seudónimo permite relacionar imágenes de una persona dentro de una cohorte y sigue siendo un dato potencialmente vinculable. El texto impreso en píxeles y los campos libres requieren revisión humana. El plan institucional debe cubrir rectificación, supresión cuando corresponda y tratamiento de copias exportadas. No se identifica un flujo de autoservicio para esos derechos en la SPA examinada.

## Ley 164 y reglamento TIC

La Ley 164, de 8 de agosto de 2011, regula telecomunicaciones y tecnologías de información y comunicación. El Decreto Supremo 1793, de 13 de noviembre de 2013, reglamenta aspectos de TIC y contiene disposiciones sobre protección de datos personales. Su alcance y el efecto de sus modificaciones deben revisarse para la entidad y el tratamiento concretos. [Ley 164 · ATT](https://www.att.gob.bo/static/LEY164.pdf) · [DS 1793 · BCB](https://www.bcb.gob.bo/webdocs/normativa/2013%20-%20DS%201793%20-%20Reglamenta%20la%20Ley%20N%C2%B0%20164.pdf) · [Normativa sobre certificación digital · ADSIB](https://desarrollo.adsib.gob.bo/paginas-web/firma-digital/quienes-somos/normativa/)

La aplicación usa credenciales individuales, contraseñas protegidas por hash, JWT con vencimiento, controles de rol, claves de entorno y bitácora de acciones. Los controles institucionales deben cubrir finalidades, base para el tratamiento, acceso del personal, circulación de exportaciones, retención e incidentes. El HTTPS, el aislamiento de red y la protección de respaldos se verifican en el despliegue.

## Manejo del expediente clínico

La Norma Técnica para el Manejo del Expediente Clínico del Ministerio de Salud y Deportes, publicada en 2008 e identificada con Resolución Ministerial N.º 00090, sirve de referencia para la custodia, confidencialidad y acceso institucional al expediente. Confirme con el hospital la normativa y los procedimientos complementarios aplicables a su establecimiento y a su historia clínica electrónica. [Norma Técnica ministerial](https://www.minsalud.gob.bo/images/Documentacion/redes_salud/NORMA%20TECNICA%20PARA%20EL%20MANEJO%20DEL%20EXPEDIENTE%20CLINICO.pdf)

El piloto utiliza un repositorio de investigación separado. Los informes y el `DiagnosticReport` de ensayo describen una salida del modelo. El personal debe identificar su procedencia y limitar las importaciones a la HCE de prueba. El ciclo de vida de las copias de investigación se acuerda con la unidad que custodia el expediente, incluyendo seudonimización, acceso y destrucción al terminar la retención.

## AGEMED y eventual clasificación del software

La Agencia Estatal de Medicamentos y Tecnologías en Salud publica orientaciones sobre registro y clasificación de dispositivos médicos. El código y el rótulo de prototipo no resuelven su clasificación regulatoria futura. Si se propone uso asistencial, transferencia o comercialización, debe verificarse con AGEMED la normativa vigente, si el uso previsto califica como software como dispositivo médico, la clase de riesgo y los requisitos de autorización, evidencia y vigilancia. No se atribuye una clase ni autorización a EcoAudit. [Circular AGEMED 82/2021](https://www.agemed.gob.bo/circulares/2021/CIRCULAR-82-2021.pdf) · [Requisitos de registro sanitario AGEMED](https://www.agemed.gob.bo/archivos_agemed/requisito%20DMI.pdf)

La ficha, el SHA-256 y el vínculo histórico modelo–análisis permiten identificar qué versión se evaluó. El ensayo documenta cambios y sus efectos. La inmutabilidad se aplica al registro de paquetes por la aplicación. Los permisos y controles del almacén deben impedir modificaciones directas no autorizadas.

## Referencias internacionales y controles

| Principio o referencia | Medida en EcoAudit | Evaluación o medida institucional |
| --- | --- | --- |
| OMS · autonomía humana | El usuario revisa el ROI y realiza su lectura independiente en I4. La interfaz advierte el carácter experimental. | Consentimiento o dispensa cuando corresponda. Verificar el cegamiento y excluir el uso en decisiones asistenciales. |
| OMS · bienestar, seguridad e interés público | Control de calidad, abstención y alerta de dominio, cuando existe referencia. | Congelar umbrales, definir interrupción del piloto y vigilar interpretaciones equivocadas. |
| OMS · transparencia, explicabilidad e inteligibilidad | Ficha, huella, probabilidad calibrada, avisos, CAM e informes. | Comunicar límites de los datos y del CAM, y documentar la interpretación de probabilidad y abstención. |
| OMS · responsabilidad y rendición de cuentas | Roles, bitácora, seudónimos y vínculo con versión. | Designar custodio, comité de seguimiento y procedimientos de acceso, incidentes y exportaciones. |
| OMS · inclusión y equidad | Cohortes y comparación I4 permiten estudiar diferencias en grupos con datos autorizados. | Preespecificar equipos, procedencias y subgrupos disponibles. Informar tamaños, incertidumbre y grupos insuficientes. |
| OMS · sostenibilidad y capacidad de respuesta | Inferencia en CPU, migraciones y recuperación de cola. | Ensayar recursos, respaldo, recuperación y revisión periódica de riesgos. |
| TRIPOD+AI · reporte de modelos de predicción | Ficha y auditoría aportan trazabilidad de versión, métricas y etiquetas. | Completar lista de verificación en el manuscrito, informar particiones, desenlace, calibración, sesgos y validación externa. |
| IEC 62304 · ciclo de vida de software | Control de versiones, requisitos, migraciones, pruebas y mantenimiento documentado. | Referencia futura para procesos formales de ciclo de vida si cambia el uso previsto. |
| ISO 14971 · gestión de riesgos | Avisos, acceso restringido, bitácora y control de versiones del modelo. | Referencia futura para un expediente formal de riesgos que abarque daños, controles, verificación y riesgo residual. |

Fuentes de los principios y estándares: [OMS, ética y gobernanza de la IA para la salud](https://www.who.int/publications/i/item/9789240029200) · [TRIPOD+AI, Collins et al., BMJ 2024](https://www.bmj.com/content/385/bmj-2023-078378) · [IEC 62304](https://www.iso.org/standard/38421.html) · [ISO 14971:2019](https://www.iso.org/standard/72704.html)

Antes del piloto, formalice aval ético, autorización del custodio, convenio de uso de datos y flujo de atención de incidentes. Defina qué datos y exportaciones se permiten, quién puede acceder, cómo se conserva la tabla de correspondencia fuera del prototipo y qué ocurre al finalizar el estudio.
