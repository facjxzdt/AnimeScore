#!/bin/bash
. .venv/bin/activate
#python3 /app/web_api/deamon.py
#python3 /app/web_api/app.py
/usr/local/bin/supervisord -c /etc/supervisord.conf