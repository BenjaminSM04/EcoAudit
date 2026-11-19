# ADR 0002: la cola de análisis es una tabla de la base de datos

**Estado:** aceptada. Reemplaza el Redis del diseño inicial.

## Contexto

El diseño inicial separaba la API del worker con una cola en Redis. El volumen esperado es bajo
(un médico analiza una imagen por vez) y cada análisis ya necesita una fila en `analyses` para
guardar su estado y su resultado.

## Decisión

La cola es la tabla `analyses` con estado `pending`. El worker reclama un trabajo con
`UPDATE … SET status='running' WHERE id=? AND status='pending'`, que es atómico tanto en
PostgreSQL como en SQLite; si no modifica ninguna fila, otro worker ya lo tomó.

## Consecuencias

- Un servicio menos que desplegar, vigilar y respaldar.
- El mismo código corre en desarrollo (SQLite, Windows) y en producción (PostgreSQL).
- Estado y resultado viven en un solo lugar: no pueden desincronizarse la cola y la base.
- El worker consulta la tabla cada segundo: añade hasta un segundo de latencia.
- No sirve para volúmenes altos. Si hiciera falta, se cambia `worker.py` sin tocar la API.
- Pendiente: reencolar los análisis que queden en `running` si el worker se interrumpe.
