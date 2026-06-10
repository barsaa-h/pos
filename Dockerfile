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

RUN mkdir -p /app/data /app/backups /app/logs /app/static/uploads && chmod 755 /app/data /app/backups /app/logs /app/static/uploads

EXPOSE 8765

ENV FLASK_ENV=production \
    POS_DB_PATH=/app/data/pos.db \
    PYTHONUNBUFFERED=1

VOLUME ["/app/data", "/app/backups"]

CMD ["gunicorn", "--bind", "0.0.0.0:8765", "--workers", "2", "--threads", "4", \
     "--access-logfile", "-", "--error-logfile", "-", \
     "--timeout", "120", \
     "app:app"]