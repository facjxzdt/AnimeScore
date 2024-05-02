#!/bin/bash
cd /app/web
gunicorn "app:create_app()"  --workers=9 --bind 0.0.0.0:5003