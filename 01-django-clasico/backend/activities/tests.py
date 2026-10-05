"""Verifica el flujo HTML real, la sesión, CSRF y el dominio del ejemplo."""
from io import StringIO
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from .models import Activity, Enrollment, Participant


class ClassicSessionTests(TestCase):
    """Pruebas exclusivas de formularios y sesión Django, sin otros mecanismos."""

    def setUp(self):
        """Crea dos cuentas y una actividad con un único cupo."""
        self.client = Client(enforce_csrf_checks=True)
        self.user = get_user_model().objects.create_user("ada@example.com", "ada@example.com", "Password123!")
        self.other = get_user_model().objects.create_user("grace@example.com", "grace@example.com", "Password123!")
        self.person = Participant.objects.create(name="Ada", user=self.user)
        self.other_person = Participant.objects.create(name="Grace", user=self.other)
        self.activity = Activity.objects.create(title="Diseño de APIs", starts_at=timezone.now(), capacity=1)

    def csrf(self, client, page="/login/"):
        """Obtiene la cookie CSRF que acompaña el formulario HTML del servidor."""
        client.get(page)
        return {"HTTP_X_CSRFTOKEN": client.cookies["auth01_csrf"].value}

    def login(self, client, email="ada@example.com"):
        """Ingresa con un formulario válido y obtiene CSRF después de su rotación."""
        response = client.post("/login/", {"email": email, "password": "Password123!"}, **self.csrf(client))
        self.assertRedirects(response, "/me/", fetch_redirect_response=False)
        return self.csrf(client, "/me/")

    def test_login_cookie_reload_expiry_and_logout(self):
        """La cookie HttpOnly restaura el acceso hasta vencer o cerrar sesión."""
        self.assertRedirects(self.client.get("/"), "/login/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/me/").status_code, 302)
        headers = self.login(self.client)
        cookie = self.client.cookies["auth01_session"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(int(cookie["max-age"]), 28800)
        self.assertContains(self.client.get("/me/"), "ada@example.com")
        restored = Client(enforce_csrf_checks=True)
        restored.cookies["auth01_session"] = cookie.value
        self.assertContains(restored.get("/me/"), "Mis inscripciones")
        self.assertEqual(self.client.post("/logout/", **headers).status_code, 302)
        self.assertFalse(Session.objects.filter(session_key=cookie.value).exists())
        self.assertEqual(restored.get("/me/").status_code, 302)
        self.login(restored)
        Session.objects.filter(session_key=restored.cookies["auth01_session"].value).update(expire_date=timezone.now())
        self.assertEqual(restored.get("/me/").status_code, 302)

    def test_registration_validates_without_logging_in(self):
        """El alta aplica validación, crea participante y requiere ingresar después."""
        new = {"name": "Nueva persona", "email": "new@example.com", "password": "Strong-Pass-2026!"}
        headers = self.csrf(self.client, "/register/")
        response = self.client.post("/register/", new, **headers)
        self.assertRedirects(response, "/login/", fetch_redirect_response=False)
        self.assertTrue(Participant.objects.filter(user__email="new@example.com").exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        duplicate = self.client.post("/register/", new, **headers)
        self.assertContains(duplicate, "El email ya está registrado.")
        weak = self.client.post("/register/", {**new, "email": "weak@example.com", "password": "123"}, **headers)
        self.assertEqual(weak.status_code, 200)
        self.assertFalse(get_user_model().objects.filter(email="weak@example.com").exists())

    def test_csrf_required_and_rotated_at_login(self):
        """Se rechazan escrituras sin token y el token previo al login deja de servir."""
        self.assertEqual(self.client.post("/register/", {}).status_code, 403)
        self.assertEqual(self.client.post("/login/", {}).status_code, 403)
        old = self.csrf(self.client)
        self.login(self.client)
        path = f"/activities/{self.activity.id}/enroll/"
        self.assertEqual(self.client.post(path).status_code, 403)
        self.assertEqual(self.client.post(path, **old).status_code, 403)
        valid = self.csrf(self.client, "/me/")
        self.assertEqual(self.client.post(path, **valid, HTTP_ORIGIN="http://attacker.invalid").status_code, 403)
        self.assertEqual(self.client.post(path, **valid).status_code, 302)
        self.assertEqual(self.client.get("/logout/").status_code, 405)

    def test_idempotency_capacity_and_ownership(self):
        """Repetir altas no duplica y otra cuenta no cancela la inscripción ajena."""
        headers = self.login(self.client)
        enroll = f"/activities/{self.activity.id}/enroll/"
        cancel = f"/activities/{self.activity.id}/unenroll/"
        for _ in range(2):
            self.assertEqual(self.client.post(enroll, **headers).status_code, 302)
        self.assertEqual(Enrollment.objects.count(), 1)
        other = Client(enforce_csrf_checks=True)
        other_headers = self.login(other, "grace@example.com")
        self.assertEqual(other.post(cancel, **other_headers).status_code, 302)
        self.assertEqual(Enrollment.objects.count(), 1)
        full = other.post(enroll, **other_headers, follow=True)
        self.assertContains(full, "No hay cupos disponibles.")
        self.assertEqual(Enrollment.objects.count(), 1)
        self.client.post(cancel, **headers)
        self.assertEqual(Enrollment.objects.count(), 0)
        other.post(enroll, **other_headers)
        self.assertEqual(Enrollment.objects.get().participant, self.other_person)

    def test_invalid_login_and_other_mechanisms_do_not_authenticate(self):
        """El ingreso falla genéricamente y no se interpretan headers de otros ejemplos."""
        headers = self.csrf(self.client)
        response = self.client.post("/login/", {"email": "ada@example.com", "password": "wrong"}, **headers)
        self.assertContains(response, "Email o contraseña incorrectos.")
        self.assertEqual(self.client.get("/me/", HTTP_AUTHORIZATION="Bearer unrelated").status_code, 302)
        for path in ["/api/v1/me", "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/service/activities"]:
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.get("/activities/").status_code, 200)

    def test_seed_is_idempotent_and_keeps_existing_passwords(self):
        """Repetir el seed conserva las cuentas y sus contraseñas modificadas."""
        output = StringIO()
        call_command("seed_activities", stdout=output)
        demo = get_user_model().objects.get(username="demo@example.com")
        demo.set_password("Changed-Pass-2026!")
        demo.save()
        count = (Activity.objects.count(), Participant.objects.count())
        call_command("seed_activities", stdout=output)
        demo.refresh_from_db()
        self.assertTrue(demo.check_password("Changed-Pass-2026!"))
        self.assertEqual(count, (Activity.objects.count(), Participant.objects.count()))
