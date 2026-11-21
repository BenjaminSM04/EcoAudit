# Hoja de ruta

## Hecho (iteración 0)

- Backend: autenticación, roles, casos, carga y de-identificación de imágenes, control de
  calidad, cola de análisis, pipeline de inferencia, registro de modelos, bitácora.
- Frontend: ingreso, casos, visor con trazado de ROI, resultado, modelos, usuarios.
- Exportador de los ensambles del estudio al formato del sistema.
- Pruebas automáticas del backend, integración continua, archivos de Docker.

## Segunda iteración

Se implementaron la importación de etiquetas sobre análisis registrados, las métricas por paciente con bootstrap estratificado, los informes PDF de análisis y cohorte, el localizador supervisado y su comparación pareada. El manuscrito y los resultados internos se encuentran en [tesis](../tesis/README.md).

## Tercera iteración

Se implementaron las cohortes en tablas propias, creadas desde análisis existentes o por lote nuevo
de hasta 1000 imágenes, con informe PDF y CSV de ítems. Se añadieron el cambio de contraseña, con
invalidación de los tokens anteriores, el restablecimiento por administrador y el límite de intentos
de ingreso. Los análisis interrumpidos se reencolan, los duplicados se buscan entre casos del mismo
usuario y el investigador puede gestionar sus propios casos.

## Cuarta iteración

Se implementaron el panel de indicadores con latencias por versión de modelo, la lectura clínica
BI-RADS ciega con concordancia médico–modelo, la exportación HL7 FHIR R4, la recepción DICOMweb
STOW-RS, la consulta de la bitácora y la comparación pareada de versiones de modelo sobre una
cohorte. La interfaz se rediseñó con un sistema de diseño propio y se documentó el proceso de
ingeniería en [docs/ingenieria](ingenieria/README.md).

## Pendientes después de la evaluación interna

1. **Migraciones con Alembic.** Hechas (0001 y 0002).
2. **Pruebas de extremo a extremo** de la interfaz. Hechas (14 flujos con Playwright).
3. **Comparación entre versiones de modelo** y evaluación formal de la cobertura de TRIPOD+AI
   en el informe de auditoría.
   - **ROI automático:** evaluarlo en un origen independiente y estudiar el entrenamiento con
     recortes fuera de pliegue.
4. **Validación externa.** Elegir un conjunto público que el proyecto nunca haya tocado, fijar el
   protocolo antes de mirar resultados y evaluar una sola vez. Con esos datos se validan también
   la zona de abstención y el umbral de cambio de dominio.
5. **Evaluación del software:** latencia, atributos de ISO/IEC 25010 y prueba de usabilidad (SUS)
   con médicos o residentes.
6. **Interoperabilidad hospitalaria:** DICOM/PACS y HL7 FHIR.
7. **Despliegue** con HTTPS y respaldos.

## Decisiones abiertas

- Umbral del aviso de cambio de dominio: hoy marca cerca del 70 % de BUS-BRA
  ([ADR 0004](adr/0004-cambio-de-dominio-por-vecinos-cercanos.md)).
- Formato y modalidad que exige la universidad para el perfil y el documento final.
- Conjunto de datos para la validación externa (candidatos: BUS-UCLM, BrEaST, UDIAT; falta
  revisar licencias y tamaños).
- Si se buscará una cohorte local, que requiere aval ético y convenio con la institución.
