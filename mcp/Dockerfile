# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------------
# Stage 1 — install dependencies into a virtualenv we can copy.
# Splitting from the runtime stage keeps the final image free of build tools
# and apt caches, and lets us keep the slim Python base.
# ----------------------------------------------------------------------------
FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build deps for cryptography (python-jose), zlib, etc. Only in builder.
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# ----------------------------------------------------------------------------
# Stage 2 — runtime. Slim base + copy venv + source.
# ----------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user — uvicorn runs unprivileged.
RUN useradd --create-home --shell /usr/sbin/nologin app
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
# V3.6 — Alembic migration runner. Without these, init_db()'s
# _run_alembic_upgrade() logs "alembic.ini not found — skipping" and the
# schema never gets V3.6 columns (archived_at, gate_*_threshold) or the
# new tables (pipeline_runs / audit_log / webhook_deliveries) migrated on
# top of existing data. Required for production Postgres.
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/

# Persist SQLite + per-instance config under /data so a volume keeps it.
RUN mkdir -p /data && chown -R app:app /app /data
USER app

ENV DATABASE_URL=sqlite+aiosqlite:////data/mcp.db
EXPOSE 8000

# Healthcheck hits the public /health route.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
