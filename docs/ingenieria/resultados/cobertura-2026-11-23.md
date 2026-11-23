# Cobertura del backend de EcoAudit · 2026-11-23

La suite completa aprobó **120 pruebas** en Windows con Python 3.11.9 y la base SQLite temporal de las pruebas. La cobertura de líneas de `app` fue **91,99 %**. El XML registró 2456 de 2670 líneas cubiertas y la terminal redondeó a 92 %. La ejecución duró 352,79 s.

Se midió el árbol de trabajo con los cambios concurrentes del backend incorporados sobre `68f011a`, con pytest 9.2.0, pytest-cov 7.1.0 y Coverage.py 7.17.4.

```powershell
# Desde backend/
.\.venv\Scripts\python.exe -m pip install pytest-cov
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-report=term --cov-report=xml
```

| Módulo | Líneas cubiertas | Líneas medibles | Cobertura en terminal |
| --- | ---: | ---: | ---: |
| `app/routers/cases.py` | 210 | 227 | 93 % |
| `app/routers/stats.py` | 141 | 150 | 94 % |
| `app/migrate.py` | 89 | 92 | 97 % |
| `app/worker.py` | 105 | 123 | 85 % |
| `app/cli.py` | 55 | 98 | 56 % |
| `app/pipeline/localizer.py` | 8 | 25 | 32 % |

La ejecución emitió un aviso de deprecación de Starlette para el uso de `httpx` con `starlette.testclient`. Este registro mide líneas ejecutadas en la suite local. El [informe de carga](carga-2026-11-23.md) documenta el ensayo Docker con PostgreSQL.
