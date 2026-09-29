FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/build.mjs ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.12-slim

LABEL org.opencontainers.image.title="AnimeScore" \
      org.opencontainers.image.description="Anime ratings, rankings and community ID mappings" \
      org.opencontainers.image.source="https://github.com/facjxzdt/AnimeScore" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    API_WORKERS=1

WORKDIR /app

# Runtime deps for parsers/network
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        build-essential \
        gcc \
        libxml2 \
        libxslt1.1 \
        libxml2-dev \
        libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies in a project-local virtualenv
COPY requirements.txt /app/requirements.txt
RUN python -m venv /app/venv \
    && /app/venv/bin/pip install --upgrade pip setuptools wheel \
    && /app/venv/bin/pip install supervisor \
    && /app/venv/bin/pip install -r /app/requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy app source
COPY . /app
COPY --from=frontend /build/dist /app/frontend/dist
COPY supervisord.conf /etc/supervisord.conf

RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh \
    && groupadd --gid 10001 animescore \
    && useradd --uid 10001 --gid animescore --create-home animescore \
    && mkdir -p /app/data/cache \
    && chown -R animescore:animescore /app/data/cache

USER 10001:10001

EXPOSE 5001

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD /app/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/v1/health/', timeout=3)"

ENTRYPOINT ["/app/entrypoint.sh"]
