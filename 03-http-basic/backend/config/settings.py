"""Configuración de una API que autentica únicamente con HTTP Basic."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "demo-only-change-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "corsheaders", "activities"]
# No hay sesiones ni middleware que autentique cookies. Basic se valida en cada vista protegida.
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")), "OPTIONS": {"timeout": 20}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",")
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_HEADERS = ["authorization", "content-type"]
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_EXPOSE_HEADERS = ["WWW-Authenticate"]
CORS_URLS_REGEX = r"^/api/"
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Ushuaia"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
