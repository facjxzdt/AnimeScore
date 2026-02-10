FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

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
COPY supervisord.conf /etc/supervisord.conf

RUN chmod +x /app/entrypoint.sh

EXPOSE 5001

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /app/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/v1/health/', timeout=3)"

ENTRYPOINT ["/app/entrypoint.sh"]
