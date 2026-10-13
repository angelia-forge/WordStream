FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN python -m pip wheel --wheel-dir /wheels .


FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATABASE_URL=sqlite:////data/wordstream.db

RUN apt-get update \
    && apt-get install --yes --no-install-recommends gosu sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 wordstream \
    && mkdir -p /app /data \
    && chown wordstream:wordstream /app /data

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts/docker-entrypoint.sh /usr/local/bin/docker-entrypoint
COPY scripts/backup_sqlite.sh /usr/local/bin/backup-sqlite

RUN chmod +x /usr/local/bin/docker-entrypoint /usr/local/bin/backup-sqlite \
    && chown -R wordstream:wordstream /app

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

ENTRYPOINT ["docker-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
