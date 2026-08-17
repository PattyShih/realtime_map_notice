#!/bin/bash
# Gunicorn entrypoint — reads WORKERS from env, defaults to 1
WORKERS="${WORKERS:-1}"

if [ "$WORKERS" = "1" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
else
    exec gunicorn app.main:app \
        --bind 0.0.0.0:8000 \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --timeout 120 \
        --graceful-timeout 30
fi
