#!/bin/sh
# La base persiste en /data: no se borra en cada arranque.
set -eu
uv run --locked manage.py migrate --noinput
uv run --locked manage.py seed_activities
exec uv run --locked manage.py runserver 0.0.0.0:8000 --noreload
