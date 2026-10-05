"""Pruebas específicas: Basic por request, CORS, autorización y dominio aislado."""
import base64
import json
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from .models import Activity, Enrollment, Participant


def basic(email, password="Password123!"):
    """Construye un header Basic de prueba sin iniciar una sesión Django."""
    value = base64.b64encode(f"{email}:{password}".encode()).decode()
    return {"HTTP_AUTHORIZATION": "Basic " + value}


class BasicAuthenticationTests(TestCase):
    """Comprueba que únicamente Basic identifica a las personas en esta carpeta."""
    def setUp(self):
        """Prepara dos personas independientes y una actividad con un único cupo."""
        self.a = get_user_model().objects.create_user(username="ada@example.com", email="ada@example.com", password="Password123!")
        self.b = get_user_model().objects.create_user(username="grace@example.com", email="grace@example.com", password="Password123!")
        Participant.objects.create(user=self.a, name="Ada")
        Participant.objects.create(user=self.b, name="Grace")
        self.activity = Activity.objects.create(title="Diseño de APIs", starts_at=timezone.now(), capacity=1)
        self.url = f"/api/v1/me/enrollments/{self.activity.id}"
        self.ha, self.hb = basic(self.a.email), basic(self.b.email)
        self.client = Client(enforce_csrf_checks=True)

    def test_basic_challenge_and_malformed_credentials(self):
        """Ausencia, corrupción o contraseña incorrecta devuelven el mismo challenge."""
        malformed = ["", "Bearer other", "Basic invalid", "Basic !!!", "Basic ", "Basic Og==", "Basic //8=", "Basic Zm9v", "Basic YTpi extra"]
        for value in malformed:
            with self.subTest(value=value):
                response = self.client.get("/api/v1/me", HTTP_AUTHORIZATION=value)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "unauthorized")
                self.assertIn('charset="UTF-8"', response["WWW-Authenticate"])
        self.assertEqual(self.client.get("/api/v1/me", **basic(self.a.email, "wrong")).status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", **self.ha).json()["email"], self.a.email)
        self.assertNotIn("Set-Cookie", self.client.get("/api/v1/me", **self.ha).headers)

    def test_each_request_revalidates_password_and_active_user(self):
        """No persiste autenticación: cambiar contraseña o desactivar invalida próximas consultas."""
        self.assertEqual(self.client.get("/api/v1/me", **self.ha).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.a.set_password("Nueva:contraseña123!")
        self.a.save()
        self.assertEqual(self.client.get("/api/v1/me", **self.ha).status_code, 401)
        valid = basic(self.a.email, "Nueva:contraseña123!")
        valid["HTTP_AUTHORIZATION"] = valid["HTTP_AUTHORIZATION"].replace("Basic", "basic")
        self.assertEqual(self.client.get("/api/v1/me", **valid).status_code, 200)
        self.a.is_active = False
        self.a.save()
        self.assertEqual(self.client.get("/api/v1/me", **valid).status_code, 401)

    def test_no_other_mechanisms_or_routes(self):
        """Cookies, bearer y API keys no autentican; endpoints ajenos no existen."""
        self.client.cookies["auth02_session"] = "fake"
        self.assertEqual(self.client.get("/api/v1/me", HTTP_X_API_KEY="fake").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/me", HTTP_AUTHORIZATION="Bearer fake").status_code, 401)
        for path in ("/api/v1/auth/login", "/api/v1/auth/logout", "/api/v1/auth/refresh", "/api/v1/auth/csrf", "/api/v1/service/activities"):
            self.assertEqual(self.client.post(path).status_code, 404)

    def test_registration_validation_and_password_hash(self):
        """Registro público valida en servidor, evita duplicados y no conserva texto de contraseña."""
        person = {"name": "Linus", "email": "linus@example.com", "password": "StrongWord123!"}
        response = self.client.post("/api/v1/auth/register", json.dumps(person), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        user = get_user_model().objects.get(username=person["email"])
        self.assertTrue(user.check_password(person["password"]))
        self.assertNotEqual(user.password, person["password"])
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
        self.assertEqual(self.client.post("/api/v1/auth/register", json.dumps(person), content_type="application/json").status_code, 409)
        for body in ("[]", "bad json", '{"name": true}', json.dumps({**person, "email": "invalid"}), json.dumps({**person, "password": "123"})):
            self.assertEqual(self.client.post("/api/v1/auth/register", body, content_type="application/json").status_code, 400)

    def test_enrollments_capacity_idempotence_and_owner(self):
        """Una identidad válida no autoriza cancelación ajena ni inscripción sin cupo."""
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
        """Errores de contrato HTTP se distinguen de una credencial incorrecta."""
        self.assertEqual(self.client.put(self.url, "{}", content_type="application/json", **self.ha).status_code, 400)
        self.assertEqual(self.client.put("/api/v1/me/enrollments/bad", **self.ha).status_code, 400)
        self.assertEqual(self.client.delete("/api/v1/enrollments/bad", **self.ha).status_code, 400)
        self.assertEqual(self.client.put(f"/api/v1/me/enrollments/{uuid4()}", **self.ha).status_code, 404)
        self.assertEqual(self.client.post("/api/v1/me", **self.ha).status_code, 405)

    def test_cors_preflight_and_error_visibility(self):
        """OPTIONS no autentica; el origen permitido puede leer también el challenge 401."""
        origin = "http://localhost:5173"
        response = self.client.options(self.url, HTTP_ORIGIN=origin, HTTP_ACCESS_CONTROL_REQUEST_METHOD="PUT", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)
        self.assertNotIn("Access-Control-Allow-Credentials", response.headers)
        self.assertIn("authorization", response["Access-Control-Allow-Headers"])
        unauthorized = self.client.get("/api/v1/me", HTTP_ORIGIN=origin)
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(unauthorized["Access-Control-Allow-Origin"], origin)
        self.assertIn("WWW-Authenticate", unauthorized["Access-Control-Expose-Headers"])
        denied = self.client.get("/api/v1/me", HTTP_ORIGIN="http://localhost:9999", **self.ha)
        self.assertEqual(denied.status_code, 200)
        self.assertNotIn("Access-Control-Allow-Origin", denied.headers)

    def test_seed_is_repeatable_and_does_not_reset_password(self):
        """Volver a levantar Docker preserva cuentas, hashes y cantidad de datos iniciales."""
        call_command("seed_activities", verbosity=0)
        demo = get_user_model().objects.get(username="demo@example.com")
        demo.set_password("ChangedPassword123!")
        demo.save()
        count = Activity.objects.count()
        call_command("seed_activities", verbosity=0)
        demo.refresh_from_db()
        self.assertTrue(demo.check_password("ChangedPassword123!"))
        self.assertEqual(Activity.objects.count(), count)
