"""Sesión y CSRF reales, con cliente que aplica la protección en los tests."""
import json
from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from .models import Activity, Enrollment, Participant


def post_json(client, path, value, **headers):
    """Envía formularios JSON de la SPA conservando las cookies del cliente."""
    return client.post(path, json.dumps(value), content_type="application/json", **headers)


class SessionAuthenticationTests(TestCase):
    """Comprueba que sesión, CSRF y autorización son controles independientes."""
    def setUp(self):
        """Prepara dos personas, una actividad de un cupo y clientes que exigen CSRF."""
        self.a = {"name": "Ada", "email": "ada@example.com", "password": "Password123!"}
        self.b = {"name": "Grace", "email": "grace@example.com", "password": "Password123!"}
        for person in (self.a, self.b):
            user = get_user_model().objects.create_user(username=person["email"], email=person["email"], password=person["password"])
            Participant.objects.create(user=user, name=person["name"])
        self.activity = Activity.objects.create(title="Diseño de APIs", starts_at=timezone.now(), capacity=1)
        self.url = f"/api/v1/me/enrollments/{self.activity.id}"
        self.client = Client(enforce_csrf_checks=True)
        self.origin = {"HTTP_ORIGIN": "http://localhost:5172"}

    def csrf(self, client):
        """Obtiene el token desde JSON como React, sin leer directamente la cookie."""
        response = client.get("/api/v1/auth/csrf", **self.origin)
        self.assertEqual(response.status_code, 200)
        return {"HTTP_X_CSRFTOKEN": response.json()["csrfToken"]}

    def sign_in(self, client, person=None):
        """Inicia sesión con CSRF y obtiene un token nuevo después de su rotación."""
        response = post_json(client, "/api/v1/auth/login", person or self.a, **self.csrf(client), **self.origin)
        self.assertEqual(response.status_code, 200)
        return self.csrf(client)

    def test_cookie_attributes_and_restoration(self):
        """La sesión es HttpOnly, Lax y tiene ocho horas; /me restaura la identidad."""
        self.sign_in(self.client)
        cookie = self.client.cookies["auth02_session"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(int(cookie["max-age"]), 8 * 3600)
        self.assertFalse(cookie["secure"])
        self.assertEqual(cookie["domain"], "")
        self.assertTrue(self.client.cookies["auth02_csrf"]["httponly"])
        response = self.client.get("/api/v1/me", **self.origin)
        self.assertEqual(response.json()["email"], self.a["email"])
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertNotIn("WWW-Authenticate", response.headers)
        self.assertEqual(self.client.get("/api/v1/me/enrollments", **self.origin).json(), [])

    @override_settings(DEBUG=False)
    def test_production_cookies_are_secure(self):
        """Los atributos de producción se configuran al cargar settings; verifica su contrato."""
        # DEBUG override no reevalúa constantes settings; simula atributos de producción.
        with override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True):
            self.sign_in(self.client)
            self.assertTrue(self.client.cookies["auth02_session"]["secure"])
            self.assertTrue(self.client.cookies["auth02_csrf"]["secure"])

    def test_login_register_and_logout_require_csrf(self):
        """Todas las escrituras, incluidos ingreso y registro, validan el token."""
        self.assertEqual(post_json(self.client, "/api/v1/auth/login", self.a, **self.origin).status_code, 403)
        new = {"name": "Linus", "email": "linus@example.com", "password": "StrongWord123!"}
        self.assertEqual(post_json(self.client, "/api/v1/auth/register", new, **self.origin).status_code, 403)
        headers = self.csrf(self.client)
        self.assertEqual(post_json(self.client, "/api/v1/auth/register", new, **headers, **self.origin).status_code, 201)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(post_json(self.client, "/api/v1/auth/register", new, **headers, **self.origin).status_code, 409)
        headers = self.sign_in(self.client)
        self.assertEqual(self.client.post("/api/v1/auth/logout", **self.origin).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout", **headers, **self.origin).status_code, 204)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.cookies["auth02_session"].value, "")

    def test_login_rotates_csrf_and_session_key(self):
        """El token previo al ingreso deja de servir para modificaciones posteriores."""
        old = self.csrf(self.client)
        old_cookie = self.client.cookies["auth02_csrf"].value
        self.assertEqual(post_json(self.client, "/api/v1/auth/login", self.a, **old, **self.origin).status_code, 200)
        self.assertNotEqual(old_cookie, self.client.cookies["auth02_csrf"].value)
        self.assertEqual(self.client.put(self.url, **old, **self.origin).status_code, 403)
        self.assertEqual(self.client.put(self.url, **self.csrf(self.client), **self.origin).status_code, 201)

    def test_wrong_origin_rejected_even_with_valid_csrf(self):
        """Confiar en un origen y validar el token son ambos requisitos de escritura."""
        headers = self.csrf(self.client)
        malicious = {"HTTP_ORIGIN": "http://localhost:9999"}
        response = post_json(self.client, "/api/v1/auth/login", self.a, **headers, **malicious)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "csrf_failed")
        headers = self.sign_in(self.client)
        self.assertEqual(self.client.put(self.url, **headers, **malicious).status_code, 403)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 200)

    def test_anonymous_expired_and_other_mechanisms(self):
        """El middleware valida CSRF primero; con token válido, la vista exige sesión."""
        # Sin CSRF, el rechazo ocurre incluso cuando tampoco hay sesión.
        for method, path in (("put", self.url), ("delete", self.url),
                             ("delete", f"/api/v1/enrollments/{self.activity.id}"),
                             ("post", "/api/v1/auth/logout")):
            response = getattr(self.client, method)(path, **self.origin)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["code"], "csrf_failed")
        # Un token CSRF no autentica: permite llegar a la vista, que devuelve 401.
        headers = self.csrf(self.client)
        self.assertEqual(self.client.put(self.url, **headers, **self.origin).status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/logout", **headers, **self.origin).status_code, 401)
        for authorization in ("Basic ZGVtbzpwYXNz", "Bearer fake"):
            response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=authorization)
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("WWW-Authenticate", response.headers)
        self.assertEqual(self.client.get("/api/v1/me", HTTP_X_API_KEY="fake").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/refresh").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/service/activities").status_code, 404)
        headers = self.sign_in(self.client)
        Session.objects.filter(session_key=self.client.cookies["auth02_session"].value).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.put(self.url, **headers, **self.origin).status_code, 401)
        self.assertEqual(self.client.put(self.url, **self.origin).status_code, 403)
        self.assertEqual(Enrollment.objects.count(), 0)

    def test_wrong_password_has_generic_401(self):
        """Contraseña incorrecta y cuenta inexistente no revelan qué dato falló."""
        headers = self.csrf(self.client)
        first = post_json(self.client, "/api/v1/auth/login", {**self.a, "password": "wrong"}, **headers, **self.origin)
        second = post_json(self.client, "/api/v1/auth/login", {**self.a, "email": "absent@example.com"}, **headers, **self.origin)
        self.assertEqual(first.status_code, 401)
        self.assertEqual(first.json(), second.json())
        self.assertNotIn("auth02_session", self.client.cookies)

    def test_enrollments_capacity_idempotence_and_ownership(self):
        """Sesión y CSRF válidos no dan permiso sobre una inscripción ajena."""
        headers = self.sign_in(self.client)
        self.assertEqual(self.client.put(self.url, **self.origin).status_code, 403)
        self.assertEqual(self.client.put(self.url, **headers, **self.origin).status_code, 201)
        self.assertEqual(self.client.put(self.url, **headers, **self.origin).status_code, 200)
        enrollment = self.client.get("/api/v1/me/enrollments").json()[0]
        other = Client(enforce_csrf_checks=True)
        other_headers = self.sign_in(other, self.b)
        self.assertEqual(other.get("/api/v1/me/enrollments").json(), [])
        self.assertEqual(other.put(self.url, **other_headers, **self.origin).status_code, 409)
        self.assertEqual(other.delete(f"/api/v1/enrollments/{enrollment['id']}", **other_headers, **self.origin).status_code, 403)
        self.assertEqual(other.delete(self.url, **other_headers, **self.origin).status_code, 204)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertEqual(self.client.delete(f"/api/v1/enrollments/{enrollment['id']}", **self.origin).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/v1/enrollments/{enrollment['id']}", **headers, **self.origin).status_code, 204)
        self.assertEqual(self.client.delete(self.url, **headers, **self.origin).status_code, 204)
        self.assertEqual(self.client.get(f"/api/v1/activities/{self.activity.id}").json()["available_slots"], 1)

    def test_cors_preflight_credentials_and_errors(self):
        """El navegador puede leer errores del origen autorizado, con cookies habilitadas."""
        response = self.client.options(self.url, **self.origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="x-csrftoken")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], self.origin["HTTP_ORIGIN"])
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        self.assertIn("x-csrftoken", response["Access-Control-Allow-Headers"])
        self.assertNotIn("authorization", response["Access-Control-Allow-Headers"])
        unauthorized = self.client.get("/api/v1/me", **self.origin)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized["Access-Control-Allow-Origin"], self.origin["HTTP_ORIGIN"])
        forbidden = post_json(self.client, "/api/v1/auth/login", self.a, **self.origin)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden["Content-Type"], "application/json")
        self.assertEqual(forbidden.json()["code"], "csrf_failed")
        self.assertEqual(forbidden["Cache-Control"], "no-store")
        self.assertEqual(forbidden["Access-Control-Allow-Origin"], self.origin["HTTP_ORIGIN"])
        denied = self.client.get("/api/v1/activities", HTTP_ORIGIN="http://localhost:9999")
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_registration_validation_and_repeatable_seed(self):
        """Valida entrada y preserva contraseñas previas durante el arranque idempotente."""
        headers = self.csrf(self.client)
        for body in ("[]", "bad json", json.dumps({**self.a, "password": "123"}), json.dumps({**self.a, "email": "invalid"})):
            self.assertEqual(self.client.post("/api/v1/auth/register", body, content_type="application/json", **headers, **self.origin).status_code, 400)
        output = StringIO()
        call_command("seed_activities", stdout=output)
        demo = get_user_model().objects.get(username="demo@example.com")
        demo.set_password("ChangedPassword123!")
        demo.save()
        count = Activity.objects.count()
        call_command("seed_activities", stdout=output)
        demo.refresh_from_db()
        self.assertTrue(demo.check_password("ChangedPassword123!"))
        self.assertEqual(Activity.objects.count(), count)
