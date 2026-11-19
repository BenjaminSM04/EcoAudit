# Contrato de API — iteración 3

Fuente única para backend y frontend. Todas las rutas exigen `Authorization: Bearer`. Errores:
`{"detail": "mensaje en español"}`. Fechas ISO 8601 con zona (UTC).

## Roles

| Ruta | medico | investigador | admin |
|---|---|---|---|
| Casos, imágenes, análisis (`/api/cases…`, `/api/images…`, `/api/analyses…`) | propios | propios | todos |
| Cohortes (`/api/cohorts…`) | no (403) | propias | todas |
| Usuarios (`/api/users…`) | no | no | sí |

"Propio" = el caso lo creó el usuario. Un recurso ajeno responde **404**, nunca 403.

## Cuenta

### `POST /api/auth/password`
Cuerpo `{"current_password": str, "new_password": str (10–128)}` → **204**.
Contraseña actual incorrecta → 400. Tras el cambio, los tokens emitidos antes dejan de valer (401)
y el frontend debe volver a iniciar sesión.

### `POST /api/users/{id}/password` (admin)
Cuerpo `{"new_password": str (10–128)}` → **204**. Invalida los tokens de ese usuario.

### Límite de intentos
`POST /api/auth/login` con 5 fallos para el mismo correo en 15 minutos → **429**
`"Demasiados intentos fallidos. Espere 15 minutos."` (también si la contraseña es correcta).

## Imágenes: banderas nuevas en `qc_flags`

- `exact_duplicate_other_case`: idéntica a una imagen de otro caso del mismo usuario.
- `near_duplicate_other_case`: casi idéntica a una imagen de otro caso del mismo usuario.

`duplicate_of_id` apunta a esa imagen. Las banderas existentes (`exact_duplicate`,
`near_duplicate`) siguen siendo para el mismo caso.

## Análisis

`AnalysisOut` agrega `attempts: int`. Un análisis interrumpido (worker caído) vuelve a la cola;
tras 3 intentos queda `failed` con `error` `"Interrumpido repetidamente."`.

## Cohortes

```ts
type CohortStatus = 'processing' | 'done' | 'failed'

interface CohortSummary {
  id: number
  name: string
  source: 'analyses' | 'batch'
  status: CohortStatus
  model: string                 // "nombre versión"
  created_at: string
  progress: { total: number; done: number; failed: number }
}

interface CohortMetrics {        // mismas claves que la versión anterior
  patients: number; positive: number; images: number
  auc: number; ci: [number, number] | null
  brier: number; ece: number
  bins: { bin: number; n: number; predicted: number; observed: number }[]
  abstentions: number
  decisions: Record<string, number>   // conteo por decision
  demo: boolean; model_hash: string; csv_hash: string
}

interface CohortDetail extends CohortSummary {
  results: CohortMetrics | null      // null mientras processing o si failed
  error: string | null
}
```

### `GET /api/cohorts` → `CohortSummary[]` (más reciente primero)
### `GET /api/cohorts/{id}` → `CohortDetail`
Si la cohorte está en `processing` y todos sus análisis terminaron, el backend calcula el
resultado en esa misma llamada.

### `POST /api/cohorts` — desde análisis existentes
Multipart: `file` (CSV `analysis_id,label`), `name` (opcional). Cada análisis debe estar
terminado, ser del usuario (salvo admin) y usar una misma versión de modelo; si no, 422 con el
número de fila (sin revelar si el análisis existe). → **201** `CohortDetail` con `status: "done"`.

### `POST /api/cohorts/batch` — lote nuevo
Multipart: `name` (obligatorio), `manifest` (CSV UTF-8 `filename,patient_ref,label`),
`images` (varios archivos; el nombre de cada archivo debe figurar en el manifiesto y viceversa).
Requiere modelo activo (409 si no hay). Límite: 1000 imágenes. Valida todo antes de guardar nada
(422 con el detalle). Crea un caso por `patient_ref` del usuario, carga las imágenes (misma
de-identificación y control de calidad), encola un análisis de imagen completa por imagen.
→ **201** `CohortDetail` con `status: "processing"`.

Si algún análisis falla, la cohorte queda `failed` con `error` `"N análisis fallaron."`.

### `GET /api/cohorts/{id}/report` → PDF (409 si no está `done`)
### `GET /api/cohorts/{id}/items.csv` → CSV
`analysis_id,patient_ref,label,probability,decision,status`
