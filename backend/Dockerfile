FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
# Migraciones de Alembic: alembic.ini y migrations/ deben quedar junto a app/ (init_db los ubica
# relativo al paquete; uvicorn y `python -m app.*` cargan /srv/app, no la copia de site-packages).
COPY alembic.ini ./
COPY migrations ./migrations
ARG ECOAUDIT_DEMO=0
RUN if [ "$ECOAUDIT_DEMO" = "1" ]; then pip install --no-cache-dir '.[demo]'; \
    else pip install --no-cache-dir .; fi

RUN useradd --create-home ecoaudit && mkdir -p /data && chown ecoaudit /data
USER ecoaudit
ENV ECOAUDIT_STORAGE_DIR=/data/storage

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
