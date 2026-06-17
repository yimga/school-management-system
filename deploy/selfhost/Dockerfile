# Self-host image for RunMyCampus (Django 5.2 + django-tenants).
# Mirrors the Render build (build.sh): Python 3.12 + Node (world-globe WebGL
# bundle, which is gitignored and must be built) + collectstatic. One image is
# reused by the web / worker / beat services in docker-compose.yml.
#
# Build context MUST be the repo root (beta/school-management-system/):
#   docker compose -f deploy/selfhost/docker-compose.yml build
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# System deps: libpq for psycopg, build tools for any C extensions, Node 20 for
# the world-globe bundle, git + curl for setup.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl ca-certificates git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (cached layer).
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Node deps for the globe bundle.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

# App source.
COPY . .

# Build the world-globe WebGL bundle + collect static (mirrors build.sh). A dummy
# SECRET_KEY lets collectstatic import settings at build time; the real one is
# injected at runtime via the env file. No DB is touched here.
RUN SECRET_KEY="build-time-collectstatic-only" \
    python scripts/purge_retired_globe_vendor_chunks.py \
    && SECRET_KEY="build-time-collectstatic-only" npm run build:world-globe \
    && SECRET_KEY="build-time-collectstatic-only" python scripts/generate_globe_earth_night_texture.py \
    && SECRET_KEY="build-time-collectstatic-only" python manage.py collectstatic --noinput

EXPOSE 10000

# Default = web. Worker/beat override `command:` in docker-compose.yml.
CMD ["bash", "deploy/selfhost/entrypoint.web.sh"]
