#!/bin/bash
cd /app
. venv/bin/activate
cd /app/next
gunicorn "app:create_app()"  --workers=4 --bind 0.0.0.0:5000