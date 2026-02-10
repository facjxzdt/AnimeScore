FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Runtime deps for parsers/network
RUN apt-get update \
    && apt-get install -y --no-install-recommends libxml2 libxslt1.1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies in a project-local virtualenv
COPY requirements.txt /app/requirements.txt
RUN python -m venv /app/venv \
    && /app/venv/bin/pip install --upgrade pip setuptools wheel \
    && /app/venv/bin/pip install supervisor \
    && /app/venv/bin/pip install -r /app/requirements.txt

# Copy app source
COPY . /app

RUN chmod +x /app/entrypoint.sh

EXPOSE 5001

ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD /app/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5001/api/v1/health/', timeout=3)"

ENTRYPOINT ["/app/entrypoint.sh"]
