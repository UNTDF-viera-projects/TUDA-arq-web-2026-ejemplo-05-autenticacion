#!/bin/sh
# Las preparaciones son idempotentes; los datos quedan en el volumen del ejemplo.
set -eu
uv run --locked manage.py migrate --noinput
uv run --locked manage.py seed_activities
exec uv run --locked manage.py runserver 0.0.0.0:8000 --noreload
