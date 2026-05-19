# RunMyCampus Companion Docker sibling (v3.37.0 Agent 4).
# Image purpose:
#   * Handshake with the RMC platform (login + MAA sign).
#   * Accept canonical CSV files (operator manually exported from SIS).
#   * Sealed-box + upload to /api/v1/migration/companion/upload/.
# Image NEVER contains: SIS scraping libraries, headless browsers,
# cookie-persistence clients, vendor login bots.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

COPY app /app/app

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
