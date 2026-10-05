#!/usr/bin/env python
import os
import sys


def main():
    """Ejecuta comandos Django dentro del entorno administrado por uv."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "No se pudo importar Django. Ejecutá uv sync --locked y uv run --locked manage.py <comando>."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
