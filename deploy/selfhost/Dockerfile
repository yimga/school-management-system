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
# the world-globe bundle, git + curl for setup. The libpango/cairo/gdk-pixbuf/ffi
# libs are WeasyPrint's runtime dependencies (requirements.txt pins WeasyPrint) —
# without them report-card / receipt PDF generation fails at runtime, not build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl ca-certificates git \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
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

# Build the world-globe WebGL bundle + compile gettext catalogs + collect static
# (mirrors build.sh). A dummy SECRET_KEY lets management commands import settings
# at build time; the real one is injected at runtime via the env file. No DB is
# touched here. compile_message_catalogs (polib, no GNU gettext needed) turns each
# locale/*/LC_MESSAGES/*.po into a fresh .mo — without it the self-hosted box would
# serve whatever stale .mo happened to be committed, so a French (or any locale)
# string committed to a .po never reached self-hosted users (the cloud build.sh
# already does this; this brings the local-first / self-host path to parity).
#
# collectstatic MUST run with DEBUG=0: off-Render DEBUG defaults to 1, under which
# settings selects the PLAIN static storage (no content hashing, no manifest). But
# the box serves with DEBUG=0 -> ForgivingCompressedManifestStaticFilesStorage,
# which requests hashed filenames (foo.<hash>.css) + a staticfiles.json manifest.
# Collecting under DEBUG=1 while serving under DEBUG=0 => every hashed URL 404s =>
# the whole UI renders unstyled. Pin DEBUG=0 here so build-time and runtime storage
# match. Guarded by apps/schools/tests/test_selfhost_static_manifest.py.
RUN SECRET_KEY="build-time-collectstatic-only" \
    python scripts/purge_retired_globe_vendor_chunks.py \
    && SECRET_KEY="build-time-collectstatic-only" npm run build:world-globe \
    && SECRET_KEY="build-time-collectstatic-only" python scripts/generate_globe_earth_night_texture.py \
    && SECRET_KEY="build-time-collectstatic-only" python manage.py compile_message_catalogs \
    && SECRET_KEY="build-time-collectstatic-only" DEBUG=0 python manage.py collectstatic --noinput

# Record WHAT THIS IMAGE IS MADE OF: SHA-256 of every shippable file plus the per-app
# migration heads, hashed into one value the OTA handshake can exchange in a header.
# Deliberately AFTER collectstatic and BEFORE the build stamp: the manifest describes the
# source tree (static/, templates/, apps/), never the collected output, so running it
# earlier would be equally correct — but running it here keeps every "what did we ship"
# artefact in one place. It is cheap (a hash pass over ~10k files) and it never fails a
# build in a way collectstatic would not have failed first.
RUN SECRET_KEY="build-time-manifest-only" DEBUG=0     python manage.py generate_system_manifest --channel stable

# Stamp the build so the running box can say what code it is. Render sets
# RENDER_GIT_COMMIT for free; nothing here ever did, so /-/version/ answered
# `commit_sha: unknown` and no operator (or support engineer) could tell which
# code a box was running. That also left resolve_deploy_commit_sha() permanently
# inert, so the post-deploy cache-buster could never tell a browser its shell was
# stale.
#
# ARG is declared HERE, after collectstatic, on purpose: an ARG invalidates the
# build cache from its declaration point onward, and BUILD_TIME changes on every
# build. Declared at the top it would re-run the Node bundle and collectstatic
# every single time.
#
# Both args are optional. With neither, the script reads .git from the build
# context (the plain path here — the context is the repo root and there is no
# .dockerignore entry for .git, precisely so this works with no operator action).
# The script never fails the build; see its docstring.
ARG GIT_COMMIT=""
ARG BUILD_TIME=""
ARG ENVIRONMENT=""
RUN GIT_COMMIT="${GIT_COMMIT}" BUILD_TIME="${BUILD_TIME}" ENVIRONMENT="${ENVIRONMENT}" \
    python scripts/write_build_stamp.py

EXPOSE 10000

# Default = web. Worker/beat override `command:` in docker-compose.yml.
CMD ["bash", "deploy/selfhost/entrypoint.web.sh"]
