"""Sesión Django entre orígenes: cookie HttpOnly, validación CSRF y autorización."""
import json
from uuid import UUID

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Activity, Enrollment, Participant


def error(code, message, status):
    """Devuelve errores JSON que la interfaz puede distinguir por código y estado."""
    return JsonResponse({"code": code, "message": message}, status=status)


def payload(request):
    """Lee un objeto JSON; rechaza datos corruptos o una estructura no esperada."""
    try:
        value = json.loads(request.body or b"{}")
        return value if isinstance(value, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


def csrf_failure(request, reason=""):
    """Devuelve JSON cuando el middleware nativo rechaza CSRF antes de la vista.

    Django valida cookie, token y origen. Esta función solo presenta el error;
    no revela el motivo interno ni sustituye la protección del middleware.
    """
    response = error("csrf_failed", "Token CSRF ausente, inválido u origen no confiable.", 403)
    response["Cache-Control"] = "no-store"
    return response


def unauthorized():
    """Devuelve 401 JSON sin challenge Basic ni credenciales alternativas."""
    response = error("unauthorized", "Acceso ausente o vencido. Ingresá nuevamente.", 401)
    response["Cache-Control"] = "no-store"
    return response


def current_user(request):
    """Resuelve exclusivamente la sesión; no considera headers Authorization/API key."""
    user = request.user
    return user if user.is_authenticated and user.is_active and Participant.objects.filter(user=user).exists() else None


def private_json(value, status=200):
    """Evita que caches HTTP conserven las respuestas privadas de una persona."""
    response = JsonResponse(value, safe=isinstance(value, dict), status=status)
    response["Cache-Control"] = "no-store"
    return response


def activity_json(activity):
    """Serializa el catálogo calculando los cupos a partir de inscripciones reales."""
    count = getattr(activity, "enrolled_count", None)
    if count is None:
        count = activity.enrollments.count()
    return {"id": str(activity.id), "title": activity.title, "starts_at": activity.starts_at.isoformat(), "capacity": activity.capacity, "available_slots": max(activity.capacity - count, 0)}


def enrollment_json(enrollment):
    """Expone identificadores para comparar la autorización por actividad y por ID."""
    return {"id": str(enrollment.id), "activity_id": str(enrollment.activity_id), "participant_id": str(enrollment.participant_id), "enrolled_at": enrollment.enrolled_at.isoformat()}


def activity_by_id(value):
    """Convierte el UUID recibido sin transformar errores de entrada en fallos 500."""
    try:
        return UUID(value), None
    except ValueError:
        return None, error("invalid_request", "ID de actividad inválido.", 400)


@require_GET
def activities(request):
    """Publica el catálogo sin pedir credenciales; cuenta inscripciones en la consulta."""
    rows = Activity.objects.annotate(enrolled_count=Count("enrollments")).order_by("starts_at")
    return JsonResponse([activity_json(activity) for activity in rows], safe=False)


@require_GET
def activity_detail(request, activity_id):
    """Consulta una actividad pública y distingue UUID inválido de actividad inexistente."""
    id_, failure = activity_by_id(activity_id)
    if failure:
        return failure
    activity = Activity.objects.annotate(enrolled_count=Count("enrollments")).filter(id=id_).first()
    return JsonResponse(activity_json(activity)) if activity else error("activity_not_found", "La actividad no existe.", 404)


@require_POST
def register(request):
    """Registra con CSRF y guarda un hash sin iniciar una sesión implícita."""
    data = payload(request)
    if data is None:
        return error("invalid_request", "JSON inválido.", 400)
    name, email, password = data.get("name"), data.get("email"), data.get("password")
    if not all(isinstance(value, str) for value in (name, email, password)):
        return error("invalid_request", "Ingresá nombre, email y contraseña.", 400)
    name, email = name.strip(), email.strip().lower()
    if not name or len(name) > 160 or len(email) > 150:
        return error("invalid_request", "Nombre o email inválido.", 400)
    user = get_user_model()(username=email, email=email)
    try:
        validate_email(email)
        validate_password(password, user)
    except ValidationError as exc:
        return error("invalid_request", " ".join(exc.messages), 400)
    try:
        with transaction.atomic():
            user = get_user_model().objects.create_user(username=email, email=email, password=password)
            participant = Participant.objects.create(user=user, name=name)
    except IntegrityError:
        return error("email_taken", "El email ya está registrado.", 409)
    return private_json({"id": str(participant.id), "email": email, "name": name}, status=201)


@require_GET
def me(request):
    """Devuelve el perfil únicamente si la cookie corresponde a una sesión vigente."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    return private_json({"id": str(user.participant.id), "name": user.participant.name, "email": user.email})


@require_GET
def enrollments(request):
    """Filtra por la persona autenticada; nunca acepta el participante del cliente."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    rows = Enrollment.objects.filter(participant=user.participant).order_by("enrolled_at")
    return private_json([enrollment_json(enrollment) for enrollment in rows])


@require_http_methods(["PUT", "DELETE"])
def enrollment_detail(request, activity_id):
    """Inscribe o cancela a la persona autenticada de manera idempotente.

    La operación agrupa comprobación de cupos y escritura en una transacción.
    select_for_update bloquea la actividad en motores que soportan ese bloqueo;
    SQLite serializa escrituras y es la opción de desarrollo de esta carpeta.
    """
    user = current_user(request)
    if user is None:
        return unauthorized()
    id_, failure = activity_by_id(activity_id)
    if failure:
        return failure
    if request.method == "PUT" and request.body:
        return error("invalid_request", "PUT no recibe body.", 400)
    with transaction.atomic():
        activity = Activity.objects.select_for_update().filter(id=id_).first()
        if activity is None:
            return error("activity_not_found", "La actividad no existe.", 404)
        if request.method == "DELETE":
            Enrollment.objects.filter(activity=activity, participant=user.participant).delete()
            return HttpResponse(status=204)
        existing = Enrollment.objects.filter(activity=activity, participant=user.participant).first()
        if existing:
            return private_json(enrollment_json(existing))
        if activity.enrollments.count() >= activity.capacity:
            return error("capacity_exhausted", "No hay cupos disponibles.", 409)
        enrollment = Enrollment.objects.create(activity=activity, participant=user.participant)
        return private_json(enrollment_json(enrollment), status=201)


@require_http_methods(["DELETE"])
def enrollment_by_id(request, enrollment_id):
    """Exige sesión, CSRF y propiedad: una persona no puede cancelar datos ajenos."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    try:
        id_ = UUID(enrollment_id)
    except ValueError:
        return error("invalid_request", "ID de inscripción inválido.", 400)
    enrollment = Enrollment.objects.filter(id=id_).first()
    if enrollment is None:
        return error("enrollment_not_found", "La inscripción no existe.", 404)
    if enrollment.participant_id != user.participant.id:
        return error("forbidden", "La inscripción pertenece a otra persona.", 403)
    enrollment.delete()
    return HttpResponse(status=204)


@ensure_csrf_cookie
@require_GET
def csrf_api(request):
    """Entrega el token en JSON; React nunca necesita leer la cookie CSRF."""
    return private_json({"csrfToken": get_token(request)})


@require_POST
def login_api(request):
    """Valida CSRF y contraseña, crea la sesión y rota el secreto CSRF de Django."""
    data = payload(request)
    if data is None:
        return error("invalid_request", "JSON inválido.", 400)
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return unauthorized()
    user = authenticate(request, username=email.strip().lower(), password=password)
    if user is None or not Participant.objects.filter(user=user).exists():
        return unauthorized()
    login(request, user)
    # login rota el secreto: el frontend solicita un token JSON nuevo después.
    get_token(request)
    return private_json({"id": str(user.participant.id), "name": user.participant.name, "email": user.email})


@require_POST
def logout_api(request):
    """Exige sesión y CSRF, invalida la sesión remota y elimina su cookie."""
    if current_user(request) is None:
        return unauthorized()
    logout(request)
    return HttpResponse(status=204)
