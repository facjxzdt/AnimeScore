#!/usr/bin/env bash
set -euo pipefail

exec /app/venv/bin/supervisord -c /etc/supervisord.conf
