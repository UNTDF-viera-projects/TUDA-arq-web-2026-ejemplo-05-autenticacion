"""API con un solo mecanismo: token aleatorio enviado explícitamente como Bearer."""
import hashlib
import json
import secrets
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .models import Activity, Enrollment, Participant, Token


def error(code, message, status):
    """Produce errores JSON que la interfaz puede explicar sin analizar HTML."""
    return JsonResponse({"code": code, "message": message}, status=status)


def payload(request):
    """Acepta un objeto JSON; rechaza formularios o cuerpos malformados."""
    if request.content_type != "application/json":
        return None
    try:
        value = json.loads(request.body or b"{}")
        return value if isinstance(value, dict) else None
    except (ValueError, UnicodeDecodeError):
        return None


def digest(value):
    """Hash SHA-256 del secreto aleatorio para buscarlo sin almacenarlo en claro."""
    return hashlib.sha256(value.encode()).hexdigest()


def request_token(request):
    """Valida Bearer, hash, vencimiento, revocación y cuenta activa en cada request."""
    authorization = request.headers.get("Authorization", "")
    scheme, separator, value = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not value or len(value) > 512:
        return None
    return Token.objects.select_related("user").filter(
        digest=digest(value), revoked_at__isnull=True,
        expires_at__gt=timezone.now(), user__is_active=True,
    ).first()


def unauthorized():
    """Indica credencial ausente, inválida, vencida o revocada sin revelar detalles."""
    response = error("unauthorized", "Credencial ausente o inválida. Volvé a ingresar.", 401)
    response["WWW-Authenticate"] = "Bearer"
    return response


def current_user(request):
    """Resuelve la cuenta y su participante exclusivamente desde el bearer opaco."""
    token = request_token(request)
    return token.user if token and Participant.objects.filter(user=token.user).exists() else None


def activity_json(activity):
    """Serializa catálogo y cupos disponibles sin revelar inscripciones de otras personas."""
    count = getattr(activity, "enrolled_count", None)
    if count is None:
        count = activity.enrollments.count()
    return {"id": str(activity.id), "title": activity.title, "starts_at": activity.starts_at.isoformat(), "capacity": activity.capacity, "available_slots": max(activity.capacity - count, 0)}


def enrollment_json(enrollment):
    """Serializa la inscripción identificando actividad y propietario."""
    return {"id": str(enrollment.id), "activity_id": str(enrollment.activity_id), "participant_id": str(enrollment.participant_id), "enrolled_at": enrollment.enrolled_at.isoformat()}


def activity_by_id(value):
    """Valida UUID antes de consultar la base; evita errores internos por IDs inválidos."""
    try:
        return UUID(value), None
    except ValueError:
        return None, error("invalid_request", "ID de actividad inválido.", 400)


@require_GET
def activities(request):
    """Lista el catálogo público con cupos calculados desde las inscripciones."""
    rows = Activity.objects.annotate(enrolled_count=Count("enrollments")).order_by("starts_at")
    return JsonResponse([activity_json(a) for a in rows], safe=False)


@require_GET
def activity_detail(request, activity_id):
    """Consulta una actividad pública o devuelve 404."""
    id_, failure = activity_by_id(activity_id)
    if failure:
        return failure
    activity = Activity.objects.annotate(enrolled_count=Count("enrollments")).filter(id=id_).first()
    return JsonResponse(activity_json(activity)) if activity else error("activity_not_found", "La actividad no existe.", 404)


def register(request):
    """Crea cuenta y perfil de forma atómica; el registro no entrega un token."""
    if request.method != "POST":
        return HttpResponse(status=405)
    data = payload(request)
    if data is None:
        return error("invalid_request", "Se requiere un objeto JSON válido.", 400)
    name, email, password = data.get("name"), data.get("email"), data.get("password")
    if not isinstance(name, str) or not isinstance(email, str) or not isinstance(password, str):
        return error("invalid_request", "Ingresá nombre, email y contraseña.", 400)
    name, email = name.strip(), email.strip().lower()
    if not name or len(name) > 160 or len(email) > 150:
        return error("invalid_request", "El nombre o email no tiene una longitud válida.", 400)
    user = get_user_model()(username=email, email=email)
    try:
        validate_email(email)
        validate_password(password, user)
    except ValidationError as exc:
        return error("invalid_request", " ".join(exc.messages), 400)
    try:
        with transaction.atomic():
            user.set_password(password)
            user.save()
            participant = Participant.objects.create(user=user, name=name)
    except IntegrityError:
        return error("email_taken", "El email ya está registrado.", 409)
    return JsonResponse({"id": str(participant.id), "email": email, "name": name}, status=201)


def login_api(request):
    """Verifica contraseña y entrega una sola vez un token aleatorio con vencimiento."""
    if request.method != "POST":
        return HttpResponse(status=405)
    data = payload(request)
    if data is None:
        return error("invalid_request", "Se requiere un objeto JSON válido.", 400)
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error("invalid_request", "Ingresá email y contraseña.", 400)
    user = authenticate(request, username=email.strip().lower(), password=password)
    if user is None or not Participant.objects.filter(user=user).exists():
        return unauthorized()
    value = secrets.token_urlsafe(32)
    Token.objects.create(digest=digest(value), user=user, expires_at=timezone.now() + timedelta(seconds=settings.OPAQUE_SECONDS))
    # El navegador guarda el secreto; la base sólo conserva su hash.
    response = JsonResponse({"token": value, "token_type": "Bearer", "expires_in": settings.OPAQUE_SECONDS})
    response["Cache-Control"] = "no-store"
    return response


def logout_api(request):
    """Revoca únicamente el token presentado; otras pestañas pueden tener otros tokens."""
    if request.method != "POST":
        return HttpResponse(status=405)
    token = request_token(request)
    if token is None:
        return unauthorized()
    token.revoked_at = timezone.now()
    token.save(update_fields=["revoked_at"])
    return HttpResponse(status=204)


@require_GET
def me(request):
    """Entrega el perfil sólo después de validar el token contra la base."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    return JsonResponse({"id": str(user.participant.id), "name": user.participant.name, "email": user.email})


def enrollments(request):
    """Lista únicamente inscripciones del participante autenticado."""
    if request.method != "GET":
        return HttpResponse(status=405)
    user = current_user(request)
    if user is None:
        return unauthorized()
    rows = Enrollment.objects.filter(participant=user.participant).order_by("enrolled_at")
    return JsonResponse([enrollment_json(e) for e in rows], safe=False)


def enrollment_detail(request, activity_id):
    """Inscribe o cancela de forma idempotente para el usuario actual y respeta el cupo."""
    if request.method not in ("PUT", "DELETE"):
        return HttpResponse(status=405)
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
            return JsonResponse(enrollment_json(existing))
        if activity.enrollments.count() >= activity.capacity:
            return error("capacity_exhausted", "No hay cupos disponibles.", 409)
        enrollment = Enrollment.objects.create(activity=activity, participant=user.participant)
        return JsonResponse(enrollment_json(enrollment), status=201)


def enrollment_by_id(request, enrollment_id):
    """Cancela por ID sólo si el participante autenticado es su propietario."""
    if request.method != "DELETE":
        return HttpResponse(status=405)
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


