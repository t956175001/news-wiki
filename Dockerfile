# --- 前端构建 ---
# Only used by the prod compose (deploy/docker-compose.prod.yml), which mounts
# /app/frontend_dist into Caddy. The dev compose (docker-compose.yml) runs
# `vite dev` on the host instead and never triggers this stage.
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 后端运行 ---
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl is only here for the container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend ./backend
# Baked to a path of its own rather than straight into ./frontend_dist: that
# path is a named volume in prod (Caddy has no other way to reach the SPA
# build), and Docker only seeds a named volume from the image's content the
# *first* time the volume is created — every deploy after that would keep
# serving whatever build happened to exist back then, no matter what this
# image contains. The volume-mounted ./frontend_dist starts empty and gets
# refreshed from this baked copy on every container start instead (see
# deploy/docker-compose.prod.yml).
COPY --from=frontend-builder /app/dist ./frontend_dist_build
RUN mkdir -p ./frontend_dist

WORKDIR /app/backend

# Static files are baked into the image so the container needs no writable
# volume. The placeholders below are only read while collectstatic renders
# settings; nothing is persisted and no database is contacted.
RUN DJANGO_ENV=prod \
    SECRET_KEY=build-only \
    DATABASE_URL=sqlite:///build.sqlite3 \
    python manage.py collectstatic --noinput

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/v1/health/ || exit 1

# Extraction runs are long; the generous timeout keeps gunicorn from killing a
# worker mid-pipeline. See ARCHITECTURE.md section 8.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "120", \
     "--access-logfile", "-"]
