"""Cliente Basic controlado: lee secretos del entorno y nunca los imprime.

Ejecutar: uv run --locked basic_client.py. BASIC_EMAIL y BASIC_PASSWORD se
obtienen de configuración privada. BASIC_API_URL por defecto es local; fuera
 de localhost se exige HTTPS. No se comparte código con el frontend.
"""
import base64
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    """Evita reenviar un header que contiene una contraseña hacia otro destino."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Rechaza redirecciones en lugar de copiar la credencial a una URL nueva."""
        return None


def main():
    """Consulta identidad e inscripciones con Basic sin imprimir el secreto ni guardarlo."""
    email, password = os.environ.get("BASIC_EMAIL", ""), os.environ.get("BASIC_PASSWORD", "")
    base = os.environ.get("BASIC_API_URL", "http://localhost:8003").rstrip("/")
    destination = urlsplit(base)
    if not email or not password:
        print("Configurá BASIC_EMAIL y BASIC_PASSWORD en tu entorno privado.", file=sys.stderr)
        return 1
    if destination.username or destination.password or destination.query or destination.fragment:
        print("La URL de API no debe contener secretos, query ni fragmento.", file=sys.stderr)
        return 1
    if destination.scheme != "https" and not (destination.scheme == "http" and destination.hostname in ("localhost", "127.0.0.1", "::1")):
        print("Fuera de la práctica local se requiere una URL HTTPS.", file=sys.stderr)
        return 1
    value = base64.b64encode(f"{email.strip().lower()}:{password}".encode("utf-8")).decode("ascii")
    opener = build_opener(NoRedirect())
    try:
        for path in ("/api/v1/me", "/api/v1/me/enrollments"):
            request = Request(base + path, headers={"Authorization": "Basic " + value})
            with opener.open(request, timeout=10) as response:
                print(json.dumps(json.load(response), ensure_ascii=False, indent=2))
    except HTTPError as exc:
        print(f"La API respondió HTTP {exc.code}; no se imprimen datos de credenciales.", file=sys.stderr)
        return 1
    except (URLError, ValueError):
        print("No se pudo consultar la API.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
