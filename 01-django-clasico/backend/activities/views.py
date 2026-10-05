"""Páginas HTML: autenticación exclusivamente por sesión Django."""
from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from .models import Activity, Enrollment, Participant


class RegisterForm(forms.Form):
    """Valida los datos de alta antes de crear una cuenta y su participante."""
    name = forms.CharField(label="Nombre", max_length=160, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(label="Email", max_length=150, widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(label="Contraseña", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_email(self):
        """Normaliza el identificador que se utilizará para ingresar."""
        return self.cleaned_data["email"].lower()

    def clean(self):
        """Aplica validadores Django considerando el usuario propuesto."""
        cleaned = super().clean()
        if cleaned.get("password"):
            user = get_user_model()(username=cleaned.get("email", ""), email=cleaned.get("email", ""))
            try:
                validate_password(cleaned["password"], user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class LoginForm(forms.Form):
    """Recoge credenciales que solo se verifican al enviar el formulario."""
    email = forms.EmailField(label="Email", max_length=150, widget=forms.EmailInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(label="Contraseña", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


@require_GET
def index(request):
    """Abre ingreso o perfil según la sesión verificada por Django."""
    return redirect("me" if request.user.is_authenticated else "login")


def catalog():
    """Calcula cupos disponibles utilizando las inscripciones del servidor."""
    activities = list(Activity.objects.annotate(enrolled_count=Count("enrollments")))
    for activity in activities:
        activity.available_slots = max(0, activity.capacity - activity.enrolled_count)
    return activities


@require_GET
def home(request):
    """Entrega el catálogo público como HTML renderizado en el servidor."""
    enrolled_ids = set()
    if request.user.is_authenticated:
        enrolled_ids = set(Enrollment.objects.filter(
            participant__user=request.user,
        ).values_list("activity_id", flat=True))
    return render(request, "activities/home.html", {
        "activities": catalog(), "enrolled_ids": enrolled_ids,
    })


@require_http_methods(["GET", "POST"])
def register(request):
    """Crea usuario y participante atómicamente y vuelve al ingreso."""
    if request.user.is_authenticated:
        return redirect("me")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        try:
            with transaction.atomic():
                user = get_user_model().objects.create_user(username=email, email=email, password=form.cleaned_data["password"])
                Participant.objects.create(user=user, name=form.cleaned_data["name"])
        except IntegrityError:
            form.add_error("email", "El email ya está registrado.")
        else:
            messages.success(request, "Cuenta creada. Ahora ingresá.")
            return redirect("login")
    return render(request, "activities/form.html", {"form": form, "registering": True, "title": "Crear cuenta"})


@require_http_methods(["GET", "POST"])
def login_view(request):
    """Verifica contraseña y crea sesión; Django rota sesión y secreto CSRF."""
    if request.user.is_authenticated:
        return redirect("me")
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(request, username=form.cleaned_data["email"].lower(), password=form.cleaned_data["password"])
        if user is not None and Participant.objects.filter(user=user).exists():
            login(request, user)
            return redirect("me")
        form.add_error(None, "Email o contraseña incorrectos.")
    return render(request, "activities/form.html", {"form": form, "registering": False, "title": "Ingresar"})


@login_required
@require_POST
def logout_view(request):
    """Invalida la sesión del servidor y elimina la cookie de este ejemplo."""
    logout(request)
    return redirect("login")


@login_required
@require_GET
def me(request):
    """Muestra participante, inscripciones propias y actividades disponibles."""
    participant = Participant.objects.filter(user=request.user).first()
    if participant is None:
        logout(request)
        return redirect("login")
    enrollments = Enrollment.objects.filter(participant=participant).select_related("activity")
    return render(request, "activities/me.html", {
        "participant": participant, "enrollments": enrollments, "activities": catalog(),
        "enrolled_ids": {enrollment.activity_id for enrollment in enrollments},
    })


@login_required
@require_POST
def enroll(request, activity_id):
    """Inscribe al participante de la sesión una sola vez si quedan cupos."""
    participant = get_object_or_404(Participant, user=request.user)
    with transaction.atomic():
        activity = get_object_or_404(Activity.objects.select_for_update(), pk=activity_id)
        if Enrollment.objects.filter(activity=activity, participant=participant).exists():
            messages.info(request, "Ya estás inscripto en esta actividad.")
        elif activity.enrollments.count() >= activity.capacity:
            messages.error(request, "No hay cupos disponibles.")
        else:
            Enrollment.objects.create(activity=activity, participant=participant)
            messages.success(request, "Inscripción confirmada.")
    return redirect("me")


@login_required
@require_POST
def unenroll(request, activity_id):
    """Cancela solo la inscripción propia; repetir no afecta a terceros."""
    participant = get_object_or_404(Participant, user=request.user)
    Enrollment.objects.filter(activity_id=activity_id, participant=participant).delete()
    messages.success(request, "Inscripción cancelada.")
    return redirect("me")
