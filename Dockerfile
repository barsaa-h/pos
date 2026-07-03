FROM python:3.12-slim-bookworm AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

FROM python:3.12-slim-bookworm

# Headless server dependencies (no GTK/WebKit needed — browser client access only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

# Create non-root user
RUN groupadd -r posuser && useradd -r -g posuser -d /app -s /sbin/nologin posuser

RUN mkdir -p /app/data /app/backups /app/logs /app/static/uploads && chown -R posuser:posuser /app

USER posuser

EXPOSE 8765

ENV FLASK_ENV=production \
    POS_DB_PATH=/app/data/pos.db \
    PYTHONUNBUFFERED=1

VOLUME ["/app/data", "/app/backups"]

STOPSIGNAL SIGTERM

# Health check: verify Flask responds on /api/health
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8765/api/health')" || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "1", "--threads", "4", \
     "--max-requests", "1000", "--max-requests-jitter", "50", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--timeout", "120", \
     "--preload", \
     "app:application"]