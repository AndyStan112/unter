FROM ghcr.io/astral-sh/uv:0.10.12 AS uv
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend ./
RUN npm run build
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY services/python/pyproject.toml services/python/uv.lock ./
RUN uv sync --frozen --no-dev
COPY services/python/alembic.ini ./alembic.ini
COPY services/python/unter ./unter
COPY --from=frontend /frontend/dist ./web
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 AGNO_TELEMETRY=false
USER 10001:10001
CMD ["sh", "-c", "exec uvicorn unter.${SERVICE_MODULE}:app --host 0.0.0.0 --port 8000 --no-access-log"]
