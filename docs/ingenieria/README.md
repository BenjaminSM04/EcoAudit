# Documentación de ingeniería de EcoAudit

EcoAudit es un prototipo de investigación de Ingeniería de Sistemas para estudiar el apoyo a la clasificación de lesiones mamarias en ecografía. Su finalidad es experimental. No es un dispositivo médico y sus resultados no deben determinar la atención de pacientes.

## Índice

| Documento | Uso |
| --- | --- |
| [01. Requisitos](01-requisitos.md) | Alcance, actores, prioridades y criterios verificables |
| [02. Casos de uso](02-casos-de-uso.md) | Flujos y alternativas |
| [03. Modelado](03-modelado.md) | Arquitectura, datos, pipeline y comportamiento |
| [04. Trazabilidad](04-trazabilidad.md) | Correspondencia entre requisitos, código y pruebas |
| [05. Metodología Scrum](05-metodologia-scrum.md) | Reconstrucción del desarrollo y planificación |
| [06. Plan de pruebas](06-plan-de-pruebas.md) | Ejecución y criterios de salida |
| [07. Evaluación ISO/IEC 25010](07-evaluacion-iso25010.md) | Métricas y formulario de resultados |
| [08. Usabilidad SUS](08-usabilidad-sus.md) | Protocolo, cuestionario y registro |
| [09. Manual de usuario](09-manual-de-usuario.md) | Operación por rol |
| [10. Manual técnico](10-manual-tecnico.md) | Instalación, operación e interoperabilidad |
| [11. Marco legal y ético](11-marco-legal-y-etico.md) | Fuentes y aplicación al piloto |
| [12. Presentación para hospitales](12-presentacion-hospitales.md) | Propuesta ejecutiva de piloto |

## Relación con el manuscrito y alcance

El [manuscrito](../../tesis/EcoAudit.docx) contiene el protocolo científico, resultados y limitaciones. La [guía de reproducción](../../tesis/README.md) identifica los datos y pesos del estudio y la [auditoría de desarrollo](../../tesis/Auditoria_BUS_BRA_60_pacientes.pdf) aporta un ejemplo reproducible. Estos anexos documentan el producto de software y preparan su evaluación. Los instrumentos y umbrales propuestos requieren ejecución y registro antes de citarlos como resultados de la tesis.

La revisión abarca la línea base `335d8c2` y el backend de la iteración 4 incorporado en `8a86fe7` el 21 de noviembre de 2026. **I4** identifica el incremento de indicadores, lectura independiente BI-RADS, exportación FHIR R4, recepción DICOMweb STOW-RS, consulta administrativa de bitácora y comparación de versiones. Se documentan los contratos del backend y los recorridos de interfaz pendientes de comprobación. La doble lectura ciega forma parte del protocolo y requiere verificar accesos y cegamiento con dos lectores. La revisión del repositorio acredita presencia de código y pruebas, sin registrar resultados de ejecución.

Fuentes de ingeniería: [arquitectura](../arquitectura.md), [hoja de ruta](../roadmap.md), [ADR](../adr/), [contrato del paquete ONNX](../model-bundle.md) y [contrato de la API hospitalaria I4](../api-hospitalaria.md). Para rutas, migraciones y permisos vigentes prevalece el código del corte.
