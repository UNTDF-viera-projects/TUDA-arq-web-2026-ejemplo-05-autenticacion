"""JWT access firmado y refresh opaco rotativo, sin sesiones ni otros mecanismos."""
import hashlib
import secrets
from datetime import timedelta
import jwt
import json
from uuid import UUID

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, F
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Activity, Enrollment, Participant, RefreshToken


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


def digest(value):
    """Obtiene SHA-256 del refresh aleatorio; nunca se almacena el secreto original."""
    return hashlib.sha256(value.encode()).hexdigest()


def make_access(user):
    """Firma un access breve con identidad y vencimiento; no guarda tokens access."""
    now = int(timezone.now().timestamp())
    return jwt.encode(
        {"sub": str(user.pk), "iat": now, "exp": now + settings.ACCESS_SECONDS,
         "iss": settings.JWT_ISSUER, "type": "access"},
        settings.JWT_SIGNING_KEY, algorithm="HS256",
    )


def access_user(value):
    """Verifica firma, algoritmo fijado y claims antes de buscar la cuenta activa.

    PyJWT decodifica y verifica firma/issuer/exp. La validación adicional exige
    tipos exactos: bool no es una fecha aunque Python lo considere un entero.
    Un JWT bien firmado con claims malformados también debe devolver 401.
    """
    try:
        claims = jwt.decode(
            value, settings.JWT_SIGNING_KEY, algorithms=["HS256"],
            issuer=settings.JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss", "type"]},
        )
        if claims.get("type") != "access":
            return None
        if type(claims["iat"]) is not int or type(claims["exp"]) is not int:
            return None
        if claims["iat"] < 0 or claims["exp"] <= claims["iat"]:
            return None
        subject = claims["sub"]
        if not isinstance(subject, str) or not subject.isascii() or not subject.isdecimal() or len(subject) > 18:
            return None
        return get_user_model().objects.filter(pk=int(subject), is_active=True).first()
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        return None


def authenticate_request(request):
    """Lee solo Bearer access: una cookie refresh nunca autentica /me."""
    parts = request.headers.get("Authorization", "").split()
    return access_user(parts[1]) if len(parts) == 2 and parts[0].lower() == "bearer" else None


def unauthorized():
    """Devuelve un 401 estable sin revelar la causa ni el secreto recibido."""
    return error("unauthorized", "Credencial ausente o inválida. Ingresá nuevamente.", 401)


def current_user(request):
    """Exige access válido, cuenta activa y su perfil de participante."""
    user = authenticate_request(request)
    return user if user and user.is_active and Participant.objects.filter(user=user).exists() else None


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


@csrf_exempt
@require_GET
def activities(request):
    """Publica el catálogo sin pedir credenciales; cuenta inscripciones en la consulta."""
    rows = Activity.objects.annotate(enrolled_count=Count("enrollments")).order_by("starts_at")
    return JsonResponse([activity_json(activity) for activity in rows], safe=False)


@csrf_exempt
@require_GET
def activity_detail(request, activity_id):
    """Consulta una actividad pública y distingue UUID inválido de actividad inexistente."""
    id_, failure = activity_by_id(activity_id)
    if failure:
        return failure
    activity = Activity.objects.annotate(enrolled_count=Count("enrollments")).filter(id=id_).first()
    return JsonResponse(activity_json(activity)) if activity else error("activity_not_found", "La actividad no existe.", 404)


@csrf_exempt
@require_POST
def register(request):
    """Crea cuenta y participante sin emitir access ni cookie de autenticación.

    Registro público exento de CSRF: no utiliza una credencial automática ni
    establece refresh. El alumno vuelve al formulario de ingreso explícito.
    """
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


@csrf_exempt
@require_GET
def me(request):
    """Devuelve el perfil solo con access válido, después de login o refresh."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    return private_json({"id": str(user.participant.id), "name": user.participant.name, "email": user.email})


@csrf_exempt
@require_GET
def enrollments(request):
    """Filtra por la persona autenticada; nunca acepta el participante del cliente."""
    user = current_user(request)
    if user is None:
        return unauthorized()
    rows = Enrollment.objects.filter(participant=user.participant).order_by("enrolled_at")
    return private_json([enrollment_json(enrollment) for enrollment in rows])


@csrf_exempt
@require_http_methods(["PUT", "DELETE"])
def enrollment_detail(request, activity_id):
    """Inscribe o cancela a la persona autenticada de manera idempotente.

    La operación agrupa comprobación de cupos y escritura en una transacción.
    El UPDATE sin cambiar capacity obtiene el bloqueo de escritura de SQLite
    antes de leer cupos. Así dos altas concurrentes no comprueban el mismo cupo.
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
        Activity.objects.filter(id=id_).update(capacity=F("capacity"))
        activity = Activity.objects.filter(id=id_).first()
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


@csrf_exempt
@require_http_methods(["DELETE"])
def enrollment_by_id(request, enrollment_id):
    """Autoriza por propietario: un JWT válido no habilita inscripciones ajenas."""
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


def csrf_failure(request, reason=""):
    """Mantiene el error CSRF en JSON para el frontend; no devuelve detalles internos."""
    return error("csrf_failed", "Token CSRF ausente o inválido, u origen no permitido.", 403)


@csrf_exempt
@require_GET
def csrf_api(request):
    """Entrega token CSRF por JSON, porque su cookie HttpOnly no se lee desde React."""
    return private_json({"csrfToken": get_token(request)})


def issue_refresh(user):
    """Crea un refresh aleatorio de alta entropía y persiste solo su hash."""
    value = secrets.token_urlsafe(32)
    RefreshToken.objects.create(
        digest=digest(value), user=user,
        expires_at=timezone.now() + timedelta(seconds=settings.REFRESH_SECONDS),
    )
    return value


def token_response(request, user, value):
    """Entrega access en JSON y refresh solo en una cookie HttpOnly con Path acotado."""
    response = private_json({"access": make_access(user), "token_type": "Bearer",
                             "expires_in": settings.ACCESS_SECONDS, "csrfToken": get_token(request)})
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME, value, max_age=settings.REFRESH_SECONDS,
        httponly=True, secure=settings.REFRESH_COOKIE_SECURE,
        samesite="Lax", path=settings.REFRESH_COOKIE_PATH,
    )
    return response


@require_POST
def login_api(request):
    """Valida contraseña y CSRF, rota CSRF y establece refresh sin iniciar sesión Django."""
    data = payload(request)
    if data is None or not isinstance(data.get("email"), str) or not isinstance(data.get("password"), str):
        return error("invalid_request", "Ingresá email y contraseña.", 400)
    user = authenticate(request, username=data["email"].strip().lower(), password=data["password"])
    if user is None or not Participant.objects.filter(user=user).exists():
        return unauthorized()
    rotate_token(request)
    return token_response(request, user, issue_refresh(user))


@require_POST
def refresh_api(request):
    """Consume un refresh una sola vez, incluso cuando dos requests llegan juntos.

    UPDATE condicional es la primera operación de la transacción. SQLite no
    implementa select_for_update: el UPDATE obtiene su bloqueo de escritura y
    solo una petición puede cambiar revoked_at de NULL a una fecha. La siguiente
    obtiene cero filas y responde 401. Nuevo refresh y consumo se confirman juntos.
    """
    value = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
    if not value:
        return unauthorized()
    now = timezone.now()
    with transaction.atomic():
        consumed = RefreshToken.objects.filter(
            digest=digest(value), revoked_at__isnull=True, expires_at__gt=now,
            user__is_active=True,
        ).update(revoked_at=now)
        if consumed != 1:
            return unauthorized()
        old = RefreshToken.objects.select_related("user").get(digest=digest(value))
        if not Participant.objects.filter(user=old.user).exists():
            return unauthorized()
        new_value = issue_refresh(old.user)
    return token_response(request, old.user, new_value)


@require_POST
def logout_api(request):
    """Revoca refresh y elimina cookie; access emitidos siguen válidos hasta exp."""
    value = request.COOKIES.get(settings.REFRESH_COOKIE_NAME, "")
    if value:
        RefreshToken.objects.filter(digest=digest(value), revoked_at__isnull=True).update(revoked_at=timezone.now())
    response = HttpResponse(status=204)
    response["Cache-Control"] = "no-store"
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path=settings.REFRESH_COOKIE_PATH, samesite="Lax")
    return response
