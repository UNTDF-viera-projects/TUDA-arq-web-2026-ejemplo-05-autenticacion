# 01 · Django clásico

Este ejemplo implementa formularios HTML, sesión Django y CSRF. El servidor renderiza la interfaz y recibe los formularios: no utiliza una API React, Basic, tokens de acceso ni API keys.

## Iniciar con Docker

Desde esta carpeta:

```bash
docker compose up --build
```

Abrí <http://localhost:8001/>. El servidor aplica las migraciones y carga datos idempotentes. Las cuentas son `demo@example.com` y `other@example.com`, ambas con `Demo12345!`. El SQLite queda en el volumen propio `auth01-django-clasico_data`.

```bash
docker compose logs -f backend
docker compose exec backend uv run --locked manage.py test activities
docker compose down
```

`docker compose down` conserva los datos. Para reiniciar exclusivamente los datos de esta carpeta, `docker compose down --volumes` elimina el volumen: es opcional y destructivo.

## Ejecutar localmente con uv

Requisitos: uv y Python 3.12 o posterior. Desde esta carpeta:

```bash
cd backend
uv sync --locked
uv run --locked manage.py migrate
uv run --locked manage.py seed_activities
uv run --locked manage.py runserver 127.0.0.1:8001
```

uv administra el entorno `.venv`; no hay que activarlo ni instalar con pip. `backend/uv.lock` fija las dependencias. El seed no cambia contraseñas existentes.

## Recorrido de usuario

1. La portada abre «Ingresar». «Crear cuenta» presenta nombre, email y contraseña por separado.
2. Registro valida la contraseña, crea usuario y participante y vuelve al ingreso. No autentica automáticamente.
3. Ingresar verifica la contraseña y establece `auth01_session`, una cookie HttpOnly. Su duración predeterminada es ocho horas (`SESSION_SECONDS=28800`). El navegador conserva el identificador; Django guarda la sesión y resuelve el participante.
4. El perfil muestra nombre y email, inscripciones propias y actividades disponibles. Inscribirse o cancelar usa un formulario POST con CSRF. El HTML actualizado refleja cupos y listas.
5. Recargar conserva acceso mientras la sesión esté vigente. Salir invalida la sesión del servidor y elimina su cookie; las páginas protegidas vuelven a redirigir al ingreso.

No se almacena la contraseña en cookies ni Web Storage. `auth01_csrf` es una cookie HttpOnly distinta de la credencial de sesión. Django incluye un token CSRF en un campo oculto de cada formulario y lo valida antes de ejecutar la vista. Al ingresar, Django rota el secreto CSRF.

## Rutas

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| GET | `/` | Redirige a ingreso o perfil |
| GET | `/activities/` | Catálogo público HTML |
| GET, POST | `/register/` | Registro con CSRF |
| GET, POST | `/login/` | Ingreso con CSRF |
| GET | `/me/` | Perfil, inscripciones y catálogo, requiere sesión |
| POST | `/logout/` | Invalida sesión, requiere CSRF |
| POST | `/activities/{activity_id}/enroll/` | Inscribe a la persona actual, requiere CSRF |
| POST | `/activities/{activity_id}/unenroll/` | Cancela solo la inscripción propia, requiere CSRF |

No hay endpoints `/api/v1/auth/*`. Una petición anónima a `/me/` obtiene una redirección `302`, no un error JSON. La cancelación usa el ID de actividad y jamás actúa sobre la inscripción de otra persona.

## Código para consultar

- [views.py](backend/activities/views.py): formularios, registro, login, sesión y autorización por participante.
- [models.py](backend/activities/models.py): actividades, participantes e inscripciones.
- [settings.py](backend/config/settings.py): middleware, nombres de cookies, duración y atributos.
- [templates](backend/activities/templates/activities/): formularios con CSRF y páginas renderizadas.
- [app.js](backend/activities/static/activities/app.js): bloquea envíos repetidos mientras llega la siguiente página y restablece botones al volver en el historial; la autenticación se verifica en Django.
- [seed_activities.py](backend/activities/management/commands/seed_activities.py): datos iniciales repetibles.
- [tests.py](backend/activities/tests.py): CSRF, expiración, logout, registro, cupos y separación de usuarios.
- [Presentación: Django clásico](../autenticacion-seguridad-arquitecturas-web.html#clasico).

## Evidencias y fallos

En DevTools, preservá Network. Login recibe `Set-Cookie: auth01_session`; una inscripción envía la cookie y `csrfmiddlewaretoken`. En Application inspeccioná HttpOnly, SameSite y vencimiento. El token CSRF es una protección de la escritura y no autentica a la persona.

Probá un POST sin CSRF: responde `403`. Un token obtenido antes del login también deja de servir después de la rotación. Otra ventana privada como la segunda cuenta no puede cancelar inscripciones ajenas ni obtener un cupo agotado. Repetir una inscripción no duplica la fila. Salir y volver a `/me/` redirige al ingreso.

## Orígenes y despliegue

Este ejemplo conserva un único origen porque Django entrega el HTML. Los ejemplos 02–06 separan React y API para observar CORS. No se agrega un proxy o una SPA a este flujo.

Para cambiar el puerto de Docker, copiá `.env.example` a `.env` y modificá `BACKEND_PORT`. En local, cambiá el puerto de `runserver`. La práctica HTTP usa cookies Secure deshabilitadas; un despliegue requiere HTTPS, `DJANGO_DEBUG=0`, clave privada y hosts propios. No usar el servidor de desarrollo Django como despliegue productivo. Cada ejemplo usa nombres de cookie distintos para evitar sobrescrituras en localhost; los puertos no aíslan cookies.

## Actualización de datos existentes

Se conserva el historial de migraciones y se agrega `0004_remove_unused_credentials`. Retira únicamente las tablas Token y ServiceKey ajenas al ejemplo. Si conservaste valores de demostración en esas tablas, respaldá la base antes de migrar. No se borra automáticamente SQLite ni se reinicia el volumen. Las referencias de migraciones antiguas son históricas; el código activo solo implementa sesión Django.

El cupo se verifica dentro de una transacción. SQLite sirve para esta práctica con un proceso de desarrollo; una aplicación con concurrencia de escrituras necesita evaluar sus garantías de bloqueo y su base de datos antes de desplegar.
