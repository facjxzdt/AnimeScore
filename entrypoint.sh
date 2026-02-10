#!/usr/bin/env bash
set -euo pipefail

exec /usr/local/bin/supervisord -c /etc/supervisord.conf
