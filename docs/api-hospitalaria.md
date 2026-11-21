# API hospitalaria de EcoAudit

EcoAudit es un prototipo de investigación. Esta API sirve para ensayos de integración y evaluación con datos de prueba.

Los ejemplos usan Bash. En `TOKEN` coloque el token de una cuenta con el rol indicado.

```bash
API=http://localhost:8000/api
TOKEN='<token>'
```

Los médicos e investigadores tienen acceso a sus propios casos. Un caso ajeno responde `404`. El administrador puede acceder a todos los casos. Una operación vedada al rol responde `403`.

## Indicadores y concordancia

```bash
curl -H "Authorization: Bearer $TOKEN" "$API/stats/overview"
curl -H "Authorization: Bearer $TOKEN" "$API/stats/performance"
curl -H "Authorization: Bearer $TOKEN" "$API/stats/concordance"
```

- **Resumen**. Devuelve totales de casos, imágenes, estados de análisis y lecturas clínicas, además del modelo activo. El calendario cuenta solicitudes por día UTC e incluye el día actual y los 29 anteriores, con ceros. Las decisiones y tasas se calculan sobre análisis terminados con resultado (`done`). La abstención cuenta `indeterminate` y la alerta cuenta `shift_flag=true`. `shift_monitored` indica cuántos análisis tuvieron una bandera disponible.
- **Desempeño**. Solo investigador y administrador. Agrupa la latencia por versión de modelo para la evaluación de eficiencia de desempeño. Tanto aquí como en el resumen, `processing` mide desde el inicio hasta el fin y `total` desde la solicitud hasta el fin. Devuelve `n`, `mean`, `p50`, `p95` y `max` en segundos. Los pares sin fechas suficientes se omiten y los estadísticos sin muestras son `null`.
- **Concordancia**. La matriz 2×2 tiene filas de sospecha clínica y columnas de sospecha del modelo, en orden «no sospechoso, sospechoso». Se considera sospechoso BI-RADS 4A o superior y la decisión `suspicious`. El acuerdo es un porcentaje de los pares en la matriz. Kappa es `null` si no se puede estimar. Los indeterminados se contabilizan en `n` y `n_indeterminate` fuera de la matriz. Los análisis fuera de dominio se excluyen. El administrador cuenta todas las lecturas admisibles y los demás usuarios cuentan las propias.

## Lectura clínica y FHIR R4

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data '{"birads":"4A","blinded":true,"notes":"Lectura independiente"}' \
  "$API/analyses/42/reading"
curl -H "Authorization: Bearer $TOKEN" "$API/analyses/42/reading"
curl -H "Authorization: Bearer $TOKEN" -H 'Accept: application/fhir+json' \
  "$API/analyses/42/fhir"
```

El médico y el administrador pueden registrar una lectura por análisis y por lector, incluso antes de que termine el análisis. Devuelve `201` al crear y `409` ante un segundo registro. El lector declara `blinded`. Las categorías válidas son `1`, `2`, `3`, `4A`, `4B`, `4C`, `5` y `6`. Las notas son opcionales y admiten hasta 2000 caracteres. El GET devuelve la lectura propia o `404`. El campo `reading` en el detalle del análisis también corresponde al usuario actual.

La exportación devuelve `application/fhir+json` con un `Bundle` de tipo `collection` si el análisis terminó y `409` si aún no tiene resultado. Incluye un paciente seudonimizado, el modelo usado, la observación del modelo, categorías BI-RADS autorizadas y el informe. El administrador exporta todas las categorías disponibles y los demás usuarios exportan la propia. Las notas se excluyen. [Especificación HL7 FHIR R4](https://hl7.org/fhir/R4/bundle.html)

## Recepción DICOMweb

Un médico o administrador puede enviar una instancia directamente o varias en un cuerpo `multipart/related`. El adaptador usa la operación de recepción STOW-RS y devuelve JSON de EcoAudit. [DICOM PS3.18, operación Store](https://dicom.nema.org/medical/dicom/current/output/chtml/part18/sect_10.5.html)

```bash
curl -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/dicom' \
  --data-binary @eco1.dcm "$API/dicomweb/studies"

{
  for archivo in eco1.dcm eco2.dcm; do
    printf '%s\r\nContent-Type: application/dicom\r\n\r\n' '--ecoaudit'
    cat "$archivo"
    printf '\r\n'
  done
  printf '%s\r\n' '--ecoaudit--'
} | curl -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: multipart/related; type="application/dicom"; boundary="ecoaudit"' \
  --data-binary @- "$API/dicomweb/studies"
```

Cada instancia requiere `PatientID`. El caso se busca dentro de la cuenta receptora con el seudónimo `PAC-` seguido de los primeros doce hexadecimales del HMAC-SHA256 del identificador con la clave del servidor. Se conservan los píxeles recodificados como PNG y las banderas de calidad, incluidas las de duplicado. El texto inscrito en los píxeles se conserva.

El JSON devuelve `instancias` con `case_id`, `image_id`, `patient_ref` y `qc_flags`, y `fallos` con `indice` (desde 1) y `motivo`. `200` indica que se guardó todo, `202` que se guardaron solo las instancias válidas y `400` que ninguna instancia pudo guardarse o que el multipart es inválido. `415` indica un tipo de contenido incorrecto. `413` indica que el cuerpo supera su límite o que hay más de 100 partes. Se aplica `ECOAUDIT_MAX_UPLOAD_MB` por instancia y cuatro veces ese valor al cuerpo multipart.

## Bitácora administrativa

```bash
curl -G -H "Authorization: Bearer $TOKEN" "$API/audit-log" \
  --data-urlencode 'user_id=3' --data-urlencode 'action=image_uploaded' \
  --data-urlencode 'desde=2026-11-01T00:00:00Z' --data-urlencode 'limit=50'
curl -G -H "Authorization: Bearer $TOKEN" "$API/audit-log.csv" \
  --data-urlencode 'action=image_uploaded' --data-urlencode 'offset=50' \
  --data-urlencode 'limit=50' -o bitacora.csv
```

Ambas rutas son exclusivas del administrador. Admiten `user_id`, `action`, `desde`, `hasta`, `limit` (100 por defecto, máximo 500) y `offset`. Los extremos temporales son inclusivos y requieren zona horaria. Las filas se ordenan de más nueva a más antigua. El total filtrado se devuelve en `total` en JSON y en `X-Total-Count` en CSV.

## Reanálisis y comparación pareada

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  --data '{"model_version_id":2}' "$API/cohorts/10/reanalyze"
curl -H "Authorization: Bearer $TOKEN" "$API/cohorts/compare?a=10&b=11"
```

El investigador puede operar sobre sus cohortes y el administrador sobre todas. El reanálisis devuelve `201` con una nueva cohorte en proceso. Conserva las imágenes, ROI, pacientes y etiquetas y encola los análisis para la versión indicada, esté activa o no. Añade la versión al nombre y acorta el prefijo si supera el límite de 120 caracteres.

La comparación requiere dos cohortes terminadas con las mismas imágenes, asignaciones de paciente y etiquetas. En caso contrario devuelve `409`. Reporta AUROC e IC del 95 % y Brier por paciente. Usa la media de logits calibrados por paciente. El IC de la diferencia B − A usa 1000 remuestreos pareados de pacientes estratificados por clase con semilla 42. El IC es `null` si alguna clase tiene menos de dos pacientes. Las tasas se calculan por imagen. La abstención de cohorte incluye `indeterminate` y `out_of_domain`, y la alerta cuenta `shift_flag=true`.
