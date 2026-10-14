"""Pruebas específicas de JWT, refresh rotativo, CSRF y autorización de inscripciones."""
import base64
import json
from datetime import timedelta
from uuid import uuid4

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone

from .api_views import digest, issue_refresh, make_access
from .models import Activity, Enrollment, Participant, RefreshToken


class JwtAuthenticationTests(TestCase):
    """Comprueba un único mecanismo con clientes que sí exigen CSRF."""

    def setUp(self):
        """Prepara dos cuentas independientes, un cupo y access firmados de prueba."""
        self.a = get_user_model().objects.create_user(username="ada@example.com", email="ada@example.com", password="Password123!")
        self.b = get_user_model().objects.create_user(username="grace@example.com", email="grace@example.com", password="Password123!")
        Participant.objects.create(user=self.a, name="Ada")
        Participant.objects.create(user=self.b, name="Grace")
        self.activity = Activity.objects.create(title="Diseño de APIs", starts_at=timezone.now(), capacity=1)
        self.url = f"/api/v1/me/enrollments/{self.activity.id}"
        self.ha = {"HTTP_AUTHORIZATION": "Bearer " + make_access(self.a)}
        self.hb = {"HTTP_AUTHORIZATION": "Bearer " + make_access(self.b)}
        self.client = Client(enforce_csrf_checks=True)
        self.origin = "http://localhost:5175"

    def csrf(self, client=None):
        """Obtiene el token JSON que corresponde a la cookie CSRF de ese cliente."""
        client = client or self.client
        return client.get("/api/v1/auth/csrf", HTTP_ORIGIN=self.origin).json()["csrfToken"]

    def post_auth(self, path, body=None, client=None, token=None):
        """Simula fetch con cookie CSRF y origen autorizado, nunca una sesión Django."""
        client = client or self.client
        return client.post(path, json.dumps(body or {}), content_type="application/json", HTTP_X_CSRFTOKEN=token or self.csrf(client), HTTP_ORIGIN=self.origin)

    def login(self, client=None):
        """Autentica por contraseña y conserva refresh en el almacén de cookies de prueba."""
        return self.post_auth("/api/v1/auth/login", {"email": self.a.email, "password": "Password123!"}, client=client)

    def test_login_csrf_cookie_attributes_and_rotation(self):
        """Login exige CSRF, rota su secreto y no crea ninguna sesión Django."""
        self.assertEqual(self.client.post("/api/v1/auth/login", "{}", content_type="application/json").status_code, 403)
        old = self.csrf()
        old_cookie = self.client.cookies["auth05_csrf"].value
        response = self.post_auth("/api/v1/auth/login", {"email": self.a.email, "password": "Password123!"}, token=old)
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.client.cookies["auth05_csrf"].value, old_cookie)
        self.assertTrue(response.cookies["auth05_refresh"]["httponly"])
        self.assertEqual(response.cookies["auth05_refresh"]["path"], "/api/v1/auth/")
        self.assertEqual(response.cookies["auth05_refresh"]["samesite"], "Lax")
        self.assertEqual(int(response.cookies["auth05_refresh"]["max-age"]), settings.REFRESH_SECONDS)
        self.assertTrue(self.client.cookies["auth05_csrf"]["httponly"])
        self.assertNotIn("sessionid", self.client.cookies)
        self.assertNotIn("auth02_session", self.client.cookies)
        self.assertEqual(self.post_auth("/api/v1/auth/refresh", token=old).status_code, 403)
        self.assertEqual(self.post_auth("/api/v1/auth/refresh", token=response.json()["csrfToken"]).status_code, 200)

    def test_access_signature_and_claim_contract(self):
        """Firma, algoritmo permitido, emisor, tipo y claims malformados se verifican."""
        now = int(timezone.now().timestamp())
        claims = {"sub": str(self.a.pk), "iat": now, "exp": now + 60, "iss": "untdf-demo", "type": "access"}
        valid = jwt.encode(claims, settings.JWT_SIGNING_KEY, algorithm="HS256")
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer " + valid).status_code, 200)
        malformed = [
            {**claims, "sub": []}, {**claims, "sub": "not-a-user"}, {**claims, "sub": "9" * 100},
            {**claims, "iat": True}, {**claims, "iat": "x"}, {**claims, "iat": now + 500},
            {**claims, "exp": True}, {**claims, "exp": "x"}, {**claims, "exp": {}},
            {**claims, "exp": now - 1}, {**claims, "iss": "another-issuer"}, {**claims, "type": "refresh"},
        ] + [{key: value for key, value in claims.items() if key != missing} for missing in claims]
        tokens = [jwt.encode(item, settings.JWT_SIGNING_KEY, algorithm="HS256") for item in malformed]
        tokens += [jwt.encode(claims, "a-different-signing-key-of-at-least-32-bytes", algorithm="HS256"), jwt.encode(claims, "x" * 64, algorithm="HS512"), "not-a-jwt", valid + "x"]
        for value in tokens:
            with self.subTest(value=value[:30]):
                response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer " + value)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthorized")
        decoded = jwt.decode(valid, settings.JWT_SIGNING_KEY, algorithms=["HS256"], issuer="untdf-demo")
        self.assertEqual(set(decoded), set(claims))
        self.assertNotIn("participant_id", decoded)

    def test_cookie_alone_wrong_mechanisms_and_inactive_user(self):
        """Refresh no autentica perfil; Basic, API keys y sesiones no son alternativas."""
        self.login()
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        basic = base64.b64encode(f"{self.a.email}:Password123!".encode()).decode()
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Basic " + basic).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", HTTP_X_API_KEY="fake").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/service/activities").status_code, 404)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.client.get("/api/v1/me", **self.ha).status_code, 401)
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)

    def test_refresh_requires_csrf_rotates_and_rejects_reuse(self):
        """Refresh guarda hash, invalida el anterior y nunca devuelve el secreto por JSON."""
        reply = self.login()
        old = self.client.cookies["auth05_refresh"].value
        self.assertTrue(RefreshToken.objects.filter(digest=digest(old)).exists())
        self.assertFalse(RefreshToken.objects.filter(digest=old).exists())
        self.assertNotIn(old, reply.content.decode())
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 403)
        response = self.post_auth("/api/v1/auth/refresh")
        self.assertEqual(response.status_code, 200)
        new = self.client.cookies["auth05_refresh"].value
        self.assertNotEqual(new, old)
        self.assertIsNotNone(RefreshToken.objects.get(digest=digest(old)).revoked_at)
        self.client.cookies["auth05_refresh"] = old
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)
        self.assertEqual(RefreshToken.objects.count(), 2)

    def test_refresh_expiration_and_missing_credential(self):
        """Sin refresh, con refresh inventado o vencido no se crea access ni nuevo refresh."""
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)
        self.client.cookies["auth05_refresh"] = "invalid"
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)
        value = issue_refresh(self.a)
        RefreshToken.objects.filter(digest=digest(value)).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.cookies["auth05_refresh"] = value
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)
        self.assertEqual(RefreshToken.objects.count(), 1)

    def test_logout_requires_csrf_and_access_remains_valid(self):
        """Logout corta renovaciones, pero no incorpora una lista de revocación de JWT."""
        response = self.login()
        header = {"HTTP_AUTHORIZATION": "Bearer " + response.json()["access"]}
        old = self.client.cookies["auth05_refresh"].value
        self.assertEqual(self.client.post("/api/v1/auth/logout").status_code, 403)
        result = self.post_auth("/api/v1/auth/logout")
        self.assertEqual(result.status_code, 204)
        self.assertEqual(result.cookies["auth05_refresh"]["max-age"], 0)
        self.assertEqual(self.client.get("/api/v1/me", **header).status_code, 200)
        self.client.cookies["auth05_refresh"] = old
        self.assertEqual(self.post_auth("/api/v1/auth/refresh").status_code, 401)

    def test_registration_no_implicit_auth_validation(self):
        """Registro público crea hash y participante sin iniciar login ni emitir cookies."""
        person = {"name": "Linus", "email": "linus@example.com", "password": "StrongWord123!"}
        response = self.client.post("/api/v1/auth/register", json.dumps(person), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.cookies), 0)
        user = get_user_model().objects.get(username=person["email"])
        self.assertTrue(user.check_password(person["password"]))
        self.assertNotEqual(user.password, person["password"])
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/register", json.dumps(person), content_type="application/json").status_code, 409)
        for body in ("[]", "bad json", '{"name": true}', json.dumps({**person, "email": "invalid"}), json.dumps({**person, "password": "123"})):
            self.assertEqual(self.client.post("/api/v1/auth/register", body, content_type="application/json").status_code, 400)

    def test_login_errors_and_origin_check(self):
        """Datos incorrectos y origen fuera de confianza se rechazan con mensajes generales."""
        self.assertEqual(self.post_auth("/api/v1/auth/login", {"email": self.a.email, "password": "bad"}).status_code, 401)
        self.assertEqual(self.post_auth("/api/v1/auth/login", {"email": []}).status_code, 400)
        token = self.csrf()
        response = self.client.post("/api/v1/auth/login", "{}", content_type="application/json", HTTP_X_CSRFTOKEN=token, HTTP_ORIGIN="http://evil.example")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "csrf_failed")

    def test_enrollment_capacity_idempotence_and_owner(self):
        """Access válido no permite borrar datos ajenos; cupo e idempotencia se conservan."""
        self.assertEqual(self.client.put(self.url).status_code, 401)
        self.assertEqual(self.client.put(self.url, **self.ha).status_code, 201)
        self.assertEqual(self.client.put(self.url, **self.ha).status_code, 200)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.get(f"/api/v1/activities/{self.activity.id}").json()["available_slots"], 0)
        self.assertEqual(self.client.put(self.url, **self.hb).status_code, 409)
        enrollment = self.client.get("/api/v1/me/enrollments", **self.ha).json()[0]
        self.assertEqual(self.client.get("/api/v1/me/enrollments", **self.hb).json(), [])
        self.assertEqual(self.client.delete(f"/api/v1/enrollments/{enrollment['id']}", **self.hb).status_code, 403)
        self.assertEqual(self.client.delete(self.url, **self.hb).status_code, 204)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.delete(f"/api/v1/enrollments/{enrollment['id']}", **self.ha).status_code, 204)
        self.assertEqual(self.client.delete(self.url, **self.ha).status_code, 204)
        self.assertEqual(self.client.put(self.url, **self.hb).status_code, 201)

    def test_invalid_ids_and_methods(self):
        """Los fallos de contrato no se convierten en un refresh ni un error interno."""
        self.assertEqual(self.client.put(self.url, "{}", content_type="application/json", **self.ha).status_code, 400)
        self.assertEqual(self.client.put("/api/v1/me/enrollments/bad", **self.ha).status_code, 400)
        self.assertEqual(self.client.delete("/api/v1/enrollments/bad", **self.ha).status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/me/enrollments/{uuid4()}", **self.ha).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/me", **self.ha).status_code, 405)

    def test_cors_preflight_and_error_visibility(self):
        """OPTIONS no exige credenciales y CORS está presente también en 401 y 403."""
        response = self.client.options(self.url, HTTP_ORIGIN=self.origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], self.origin)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        unauthorized = self.client.get("/api/v1/me", HTTP_ORIGIN=self.origin)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized["Access-Control-Allow-Origin"], self.origin)
        rejected = self.client.post("/api/v1/auth/login", HTTP_ORIGIN=self.origin)
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(rejected["Access-Control-Allow-Origin"], self.origin)
        denied = self.client.get("/api/v1/me", HTTP_ORIGIN="http://localhost:9999", **self.ha)
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_seed_repeatable_and_preserves_password(self):
        """Reiniciar Docker conserva usuarios y contraseñas, sin emitir refresh nuevos."""
        call_command("seed_activities", verbosity=0)
        demo = get_user_model().objects.get(username="demo@example.com")
        demo.set_password("ChangedPassword123!")
        demo.save()
        count = Activity.objects.count()
        call_command("seed_activities", verbosity=0)
        demo.refresh_from_db()
        self.assertTrue(demo.check_password("ChangedPassword123!"))
        self.assertEqual(Activity.objects.count(), count)
        self.assertEqual(RefreshToken.objects.count(), 0)
