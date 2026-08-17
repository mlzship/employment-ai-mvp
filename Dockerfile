FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_PATH=/app/runtime/employment_ai.db \
    SEED_XLSX=/app/data/synthetic/employment_ai_demo.xlsx \
    ONTOLOGY_PATH=/app/data/ontology/employment_ontology.json

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
RUN python -m pip install --upgrade pip && python -m pip install .

RUN mkdir -p /app/runtime && chown -R app:app /app
USER app

EXPOSE 8000
VOLUME ["/app/runtime"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import json,urllib.request; r=urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3); assert json.load(r)['status']=='ok'"

CMD ["sh", "-c", "uvicorn employment_ai.main:app --host ${APP_HOST} --port ${APP_PORT}"]
