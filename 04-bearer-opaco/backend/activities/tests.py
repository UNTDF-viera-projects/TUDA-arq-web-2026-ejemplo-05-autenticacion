"""Pruebas del contrato opaco y de autorización del dominio, sin selectores de modo."""
import hashlib
import json
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import Activity, Enrollment, Participant, Token


class OpaqueApiTests(TestCase):
    """Comprueba emisión, revocación, vencimiento, permisos, CORS y aislamiento."""

    def setUp(self):
        """Crea dos usuarios y una actividad de un solo cupo para observar permisos."""
        self.user = get_user_model().objects.create_user(username="ana@example.com", email="ana@example.com", password="Demo12345!")
        self.participant = Participant.objects.create(user=self.user, name="Ana")
        self.other = get_user_model().objects.create_user(username="other@example.com", email="other@example.com", password="Demo12345!")
        self.other_participant = Participant.objects.create(user=self.other, name="Otra persona")
        self.activity = Activity.objects.create(title="Taller", starts_at=timezone.now(), capacity=1)

    def login(self, email="ana@example.com", password="Demo12345!"):
        """Entrega un token real a partir del login público de la API."""
        return self.client.post("/api/v1/auth/login", json.dumps({"email": email, "password": password}), content_type="application/json")

    def bearer(self):
        """Construye el header explícito que utiliza también React."""
        return {"HTTP_AUTHORIZATION": "Bearer " + self.login().json()["token"]}

    def test_emission_hash_and_profile(self):
        """El secreto no se persiste en claro; /me valida el token y no crea cookies."""
        response = self.login()
        raw = response.json()["token"]
        stored = Token.objects.get()
        self.assertEqual(stored.digest, hashlib.sha256(raw.encode()).hexdigest())
        self.assertNotEqual(stored.digest, raw)
        self.assertEqual(response.json()["expires_in"], 3600)
        self.assertFalse(response.cookies)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {raw}").json()["name"], "Ana")

    def test_invalid_expired_revoked_inactive_tokens(self):
        """Cada condición de invalidez produce 401 sin recuperar identidad por cookies."""
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer invalid").status_code, 401)
        headers = self.bearer()
        token = Token.objects.get()
        token.expires_at = timezone.now() - timedelta(seconds=1)
        token.save()
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 401)
        token.expires_at = timezone.now() + timedelta(hours=1)
        token.revoked_at = timezone.now()
        token.save()
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 401)
        token.revoked_at = None
        token.save()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get("/api/v1/me", **headers).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout", **headers).status_code, 401)

    def test_logout_revokes_only_presented_token(self):
        """Logout no invalida otros tokens de la misma cuenta ni crea sesión."""
        first, second = self.bearer(), self.bearer()
        self.assertEqual(self.client.post("/api/v1/auth/logout", **first).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/me", **first).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", **second).status_code, 200)
        self.assertEqual(Token.objects.filter(revoked_at__isnull=False).count(), 1)

    def test_register_validation_then_explicit_login(self):
        """Registrar no autentica; valida email y contraseña antes de crear ambos registros."""
        data = {"name": "Nueva", "email": "nueva@example.com", "password": "Demo12345!"}
        response = self.client.post("/api/v1/auth/register", json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.cookies)
        self.assertFalse(Token.objects.exists())
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/register", json.dumps(data), content_type="application/json").status_code, 409)
        for field, value in [("password", "12345678"), ("password", []), ("email", "bad"), ("name", {})]:
            invalid = {**data, "email": "new@example.com", field: value}
            self.assertEqual(self.client.post("/api/v1/auth/register", json.dumps(invalid), content_type="application/json").status_code, 400)
        self.assertEqual(self.login("nueva@example.com").status_code, 200)
        self.assertEqual(self.login(password="wrong").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/login", '{', content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/v1/auth/login", {"email": "ana@example.com"}).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/auth/login").status_code, 405)

    def test_enrollment_idempotence_capacity_and_isolation(self):
        """Repetir PUT no consume otro cupo; otro usuario no cancela la inscripción."""
        headers = self.bearer()
        path = f"/api/v1/me/enrollments/{self.activity.id}"
        response = self.client.put(path, **headers)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.put(path, **headers).status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.get("/api/v1/activities").json()[0]["available_slots"], 0)
        other_headers = {"HTTP_AUTHORIZATION": "Bearer " + self.login("other@example.com").json()["token"]}
        self.assertEqual(self.client.get("/api/v1/me/enrollments", **other_headers).json(), [])
        self.assertEqual(self.client.put(path, **other_headers).status_code, 409)
        self.assertEqual(self.client.delete(f"/api/v1/enrollments/{response.json()['id']}", **other_headers).status_code, 403)
        self.assertEqual(self.client.delete(path, **other_headers).status_code, 204)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.delete(path, **headers).status_code, 204)
        self.assertEqual(self.client.delete(path, **headers).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/activities").json()[0]["available_slots"], 1)

    def test_invalid_and_missing_domain_ids(self):
        """IDs inválidos y recursos inexistentes devuelven errores de contrato."""
        headers = self.bearer()
        for value, status in [("bad", 400), (str(uuid4()), 404)]:
            self.assertEqual(self.client.put(f"/api/v1/me/enrollments/{value}", **headers).status_code, status)
            self.assertEqual(self.client.delete(f"/api/v1/enrollments/{value}", **headers).status_code, status)
        self.assertEqual(self.client.put(f"/api/v1/me/enrollments/{self.activity.id}", "{}", content_type="application/json", **headers).status_code, 400)

    def test_foreign_routes_and_credentials_are_rejected(self):
        """No hay refresh, CSRF endpoint ni autenticación Basic o con clave de servicio."""
        for path in ["/auth/refresh", "/auth/csrf", "/service/activities"]:
            self.assertEqual(self.client.get("/api/v1" + path).status_code, 404)
        for header in [{"HTTP_AUTHORIZATION": "Basic YTpi"}, {"HTTP_X_API_KEY": "key"}, {"HTTP_COOKIE": "sessionid=anything"}]:
            self.assertEqual(self.client.get("/api/v1/me", **header).status_code, 401)
        self.assertEqual(set(field.name for field in Token._meta.fields), {"id", "digest", "user", "expires_at", "revoked_at"})

    def test_cors_preflight_error_and_denied_origin(self):
        """CORS permite origen exacto y preflight sin token, también sobre un 401."""
        response = self.client.options("/api/v1/me", HTTP_ORIGIN="http://localhost:5174", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5174")
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        response = self.client.get("/api/v1/me", HTTP_ORIGIN="http://localhost:5174")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Access-Control-Allow-Origin"], "http://localhost:5174")
        self.assertNotIn("Access-Control-Allow-Origin", self.client.get("/api/v1/me", HTTP_ORIGIN="http://localhost:9000").headers)

    def test_seed_does_not_duplicate_or_reset_password(self):
        """Repetir datos de clase conserva una contraseña modificada por el alumno."""
        call_command("seed_activities", verbosity=0)
        demo = get_user_model().objects.get(username="demo@example.com")
        demo.set_password("Custom12345!")
        demo.save()
        before = (Activity.objects.count(), Participant.objects.count())
        call_command("seed_activities", verbosity=0)
        demo.refresh_from_db()
        self.assertEqual(before, (Activity.objects.count(), Participant.objects.count()))
        self.assertTrue(demo.check_password("Custom12345!"))
