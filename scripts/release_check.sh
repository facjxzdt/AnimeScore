#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN=".venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

echo "[1/3] Python syntax check"
find apis apps data utils web web_api next -name "*.py" -print0 | xargs -0 "$PYTHON_BIN" -m py_compile

echo "[2/3] API import check"
"$PYTHON_BIN" - <<'PY'
import importlib

mods = [
    "web_api.main",
    "web_api.api_v1.router",
    "web_api.api_v1.endpoints.search",
    "apis.precise",
]
for m in mods:
    importlib.import_module(m)
print("import check: ok")
PY

echo "[3/3] Quick docs check"
grep -q "/api/v1/search" API_V1.md
grep -q "python start_api.py" README.md
echo "docs check: ok"

echo "release check passed"
