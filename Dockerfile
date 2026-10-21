# syntax=docker/dockerfile:1.7
# ============================================================
# Steam Tracker (Django) — Docker image
# Python 3.11-slim, runs both the gunicorn web server and
# the long-running scheduler (one of them per container —
# picked by docker-compose's `command:` per service).
# ============================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=steamtracker.settings

# System deps:
#   - fonts-noto-cjk + fonts-dejavu (for matplotlib CJK fallback)
#   - tini (PID 1 signal reaping — so SIGTERM reaches Django)
#   - curl (for healthcheck)
#   - ca-certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        fonts-dejavu \
        tini \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Django project.
COPY . .

# Create the persistent data + media + logs dirs and chown them.
RUN useradd -m -u 10001 tracker \
    && mkdir -p /app/data /app/media /app/logs /app/staticfiles \
    && chown -R tracker:tracker /app

USER tracker

# Collect static assets into STATIC_ROOT for WhiteNoise in production.
RUN python manage.py collectstatic --noinput

# Default entrypoint = gunicorn serving the Django app on :9000.
# Override per-service via `command:` in docker-compose.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "--bind", "0.0.0.0:9000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "steamtracker.wsgi:application"]

# Healthcheck: ping the root URL.
HEALTHCHECK --interval=60s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:9000/ || exit 1
