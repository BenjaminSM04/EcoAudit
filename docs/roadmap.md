# Hoja de ruta

## Hecho (iteración 0)

- Backend: autenticación, roles, casos, carga y de-identificación de imágenes, control de
  calidad, cola de análisis, pipeline de inferencia, registro de modelos, bitácora.
- Frontend: ingreso, casos, visor con trazado de ROI, resultado, modelos, usuarios.
- Exportador de los ensambles del estudio al formato del sistema.
- Pruebas automáticas del backend, integración continua, archivos de Docker.

## Segunda iteración

Se implementaron la importación de etiquetas sobre análisis registrados, las métricas por paciente con bootstrap estratificado, los informes PDF de análisis y cohorte, el localizador supervisado y su comparación pareada. El manuscrito y los resultados internos se encuentran en [tesis](../tesis/README.md).

## Pendientes después de la evaluación interna

1. **Auditoría.** Comparación pareada interactiva entre versiones, revisión de casi duplicados entre casos y evaluación formal de la cobertura de TRIPOD+AI.
2. **ROI automático.** Evaluar el sistema en un origen independiente y estudiar el entrenamiento con recortes fuera de pliegue.
3. **Validación externa.** Elegir un conjunto público que el proyecto nunca haya tocado, fijar el
   protocolo antes de mirar resultados y evaluar una sola vez. Con esos datos se validan también
   la zona de abstención y el umbral de cambio de dominio.
4. **Robustez:** migraciones con Alembic, reencolado de análisis interrumpidos, cambio de
   contraseña, límite de intentos de ingreso, pruebas de extremo a extremo de la interfaz.
5. **Evaluación del software:** latencia, atributos de ISO/IEC 25010 y prueba de usabilidad (SUS)
   con médicos o residentes.

## Decisiones abiertas

- Umbral del aviso de cambio de dominio: hoy marca cerca del 70 % de BUS-BRA
  ([ADR 0004](adr/0004-cambio-de-dominio-por-vecinos-cercanos.md)).
- Formato y modalidad que exige la universidad para el perfil y el documento final.
- Conjunto de datos para la validación externa (candidatos: BUS-UCLM, BrEaST, UDIAT; falta
  revisar licencias y tamaños).
- Si se buscará una cohorte local, que requiere aval ético y convenio con la institución.
