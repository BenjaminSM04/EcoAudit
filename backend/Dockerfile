FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN useradd --create-home ecoaudit && mkdir -p /data && chown ecoaudit /data
USER ecoaudit
ENV ECOAUDIT_STORAGE_DIR=/data/storage

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
