"""API JWT entre orígenes: access Bearer y refresh por cookie con CSRF."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "demo-only-change-in-production")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "auth05-demo-signing-key-change-for-production-32-bytes")
if not DEBUG and ("JWT_SIGNING_KEY" not in os.environ or len(JWT_SIGNING_KEY.encode()) < 32):
    raise ImproperlyConfigured("Configurá una JWT_SIGNING_KEY privada de al menos 32 bytes.")
JWT_ISSUER = "untdf-demo"
ACCESS_SECONDS = int(os.environ.get("ACCESS_SECONDS", "60"))
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "604800"))
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "corsheaders", "activities"]
# Sin sesiones ni AuthenticationMiddleware: la cookie refresh NO autentica las vistas.
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "corsheaders.middleware.CorsMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware"]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")), "OPTIONS": {"timeout": 20}}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5175").split(",")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = ["authorization", "content-type", "x-csrftoken"]
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
CORS_URLS_REGEX = r"^/api/"
CSRF_TRUSTED_ORIGINS = os.environ.get("CSRF_TRUSTED_ORIGINS", "http://localhost:5175").split(",")
CSRF_COOKIE_NAME = "auth05_csrf"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_FAILURE_VIEW = "activities.api_views.csrf_failure"
REFRESH_COOKIE_NAME = "auth05_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth/"
REFRESH_COOKIE_SECURE = not DEBUG
LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Ushuaia"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
