# Autenticación: cinco ejemplos independientes

Material de consulta de Arquitecturas Web, UNTDF. Cada carpeta contiene su propio backend, dependencias, configuración, base de datos, pruebas y Docker. Podés copiar un ejemplo fuera de este repositorio y ejecutarlo sin los otros.

La [presentación HTML](autenticacion-seguridad-arquitecturas-web.html) introduce CSRF antes de los mecanismos, incluye diagramas cliente–servidor y enlaza cada implementación. La [presentación complementaria de API key, OAuth y OpenID Connect](api-key-oauth-openid-connect.html) sirve de referencia para ampliar el contexto y mostrar patrones de identidad de servicio y acceso delegado. La [spec](SPEC-autenticacion.md) registra los requisitos y los criterios de aceptación.

## Presentaciones de referencia para los alumnos

- [autenticacion-seguridad-arquitecturas-web.html](autenticacion-seguridad-arquitecturas-web.html): recorrido visual de los mecanismos de autenticación y autorización estudiados en 01–05.
- [api-key-oauth-openid-connect.html](api-key-oauth-openid-connect.html): material de apoyo para API keys, OAuth 2.0 y OpenID Connect, con ejemplos y referencias de uso real.

## Ejemplos y almacenamiento

| Ejemplo                                            | Credencial y almacenamiento                                             | Continuidad y salida                                           | CSRF                                         |
| -------------------------------------------------- | ----------------------------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------- |
| [01 · Django clásico](01-django-clasico/README.md) | Cookie HttpOnly `auth01_session`; sesión Django en servidor             | Recarga conserva sesión vigente; logout la invalida            | Formularios HTML                             |
| [02 · API con sesión](02-cookie-sesion/README.md)  | Cookie HttpOnly `auth02_session`; React consulta `/me`                  | Recarga recupera perfil; logout invalida sesión                | Registro, login, logout y escrituras         |
| [03 · HTTP Basic](03-http-basic/README.md)         | Base64 de email:contraseña en `sessionStorage` → `Authorization: Basic` | Recarga verifica nuevamente; salida borra copia local          | Este cliente agrega el header explícitamente |
| [04 · Bearer opaco](04-bearer-opaco/README.md)     | Token en `sessionStorage` → `Authorization: Bearer`; hash persistido    | Recarga valida token; expiración exige ingresar; logout revoca | Este cliente agrega el header explícitamente |
| [05 · JWT + refresh](05-jwt-refresh/README.md)     | Access en memoria → Bearer; refresh en cookie HttpOnly                  | Recarga renueva access; logout invalida refresh                | Login, refresh y logout                      |

El ejemplo de sesión sin proxy forma parte de 02; no hay una carpeta 02.5. Basic y token opaco conservan acceso en la misma pestaña al recargar. `sessionStorage` es accesible a JavaScript y no protege contra XSS; en Basic contiene la contraseña reversible. Sus README explican los límites y el contexto de uso. Los clientes HTTP de 03 obtienen secretos de configuración privada y nunca de variables públicas `VITE_*`.

## Interfaz y dominio

01–05 muestran formularios separados de ingreso y registro. Después del ingreso aparecen nombre y email, inscripciones propias, cancelación y actividades con cupos para inscribirse. Sus estilos son similares y se mantienen en archivos locales independientes. El único mecanismo de autenticación de cada carpeta es el que enseña.

En 01 el servidor entrega HTML. En 02–05 React consume JSON. Cada cuenta tiene un `Participant`: el backend lo obtiene de la credencial verificada; no acepta un `user_id` o `X-Participant-ID` para elegir a quién inscribir. Las cuentas iniciales son `demo@example.com` y `other@example.com`, ambas con `Demo12345!`. El seed no cambia contraseñas existentes.

La referencia teórica para identidad de servicio y flujo delegado queda en [api-key-oauth-openid-connect.html](api-key-oauth-openid-connect.html), mientras que los ejemplos prácticos de la materia se centran en 01–05.

## Puesta en marcha

Requisito principal: Docker con Compose y el motor iniciado. Desde la carpeta que quieras estudiar:

```bash
docker compose up --build
```

Migraciones y datos iniciales se aplican al arrancar. Cada ejemplo usa un volumen SQLite propio y puertos distintos, por lo que se pueden comparar simultáneamente.

| Ejemplo | Interfaz                | API o servidor                   |
| ------- | ----------------------- | -------------------------------- |
| 01      | <http://localhost:8001> | HTML Django en el mismo servidor |
| 02      | <http://localhost:5172> | <http://localhost:8002>          |
| 03      | <http://localhost:5173> | <http://localhost:8003>          |
| 04      | <http://localhost:5174> | <http://localhost:8004>          |
| 05      | <http://localhost:5175> | <http://localhost:8005>          |

React hace requests directos a la API, sin proxy `/api`. Los README explican `VITE_API_BASE_URL`, CORS, preflight, cookies y CSRF. Usá `localhost` consistentemente: cambiarlo por `127.0.0.1` cambia el origen permitido. Los nombres de cookies son propios de cada ejemplo porque las cookies no se aíslan por puerto.

```bash
docker compose logs -f
docker compose down
```

`down` conserva los datos. `docker compose down --volumes` los elimina y se usa únicamente para un reinicio elegido de la carpeta. Para cambiar puertos, consultá su `.env.example` y README: URL de API, origen CORS y confianza CSRF deben seguir siendo coherentes.

También se puede ejecutar localmente con uv, Python 3.12 o posterior y, para React, Node y pnpm. Los proyectos Python tienen `pyproject.toml` y `uv.lock`; el entorno es administrado por uv. Las instrucciones de cada carpeta usan `uv sync --locked` y `uv run --locked`, sin pip ni activación manual.

## Contrato de las APIs de usuario: 02–05

| Método | Ruta                                   | Resultado                                        |
| ------ | -------------------------------------- | ------------------------------------------------ |
| GET    | `/api/v1/activities`                   | Catálogo público                                 |
| GET    | `/api/v1/activities/{activity_id}`     | Detalle público                                  |
| POST   | `/api/v1/auth/register`                | Alta de cuenta y participante, sin autologin     |
| GET    | `/api/v1/me`                           | Perfil autenticado                               |
| GET    | `/api/v1/me/enrollments`               | Inscripciones propias                            |
| PUT    | `/api/v1/me/enrollments/{activity_id}` | `201` nueva, `200` existente; cupo agotado `409` |
| DELETE | `/api/v1/me/enrollments/{activity_id}` | Cancela solo la propia; `204` idempotente        |
| DELETE | `/api/v1/enrollments/{enrollment_id}`  | Dueño `204`; otro usuario `403`                  |

Las rutas de autenticación son propias de cada mecanismo; Basic no publica login/logout/refresh. Para mostrar un `403` por propiedad usá el ID de una inscripción ajena en `/enrollments/{enrollment_id}`. La cancelación bajo `/me` con un ID de actividad actúa exclusivamente sobre la persona actual.

## Verificación y límites

Desde la carpeta del ejemplo:

```bash
docker compose exec backend uv run --locked manage.py test activities
```

En 02–05, también:

```bash
docker compose exec frontend pnpm build
docker compose exec frontend pnpm lint
```

Las pruebas Django corresponden únicamente al mecanismo de esa carpeta; los recorridos manuales y de DevTools están en su README. [Resultados de implementación y verificación](VERIFICACION.md) registra las comprobaciones ejecutadas y sus límites.

Las migraciones históricas se conservan; migraciones nuevas retiran modelos ajenos sin borrar automáticamente SQLite. Respaldá cualquier dato de demostración que hayas guardado en las tablas retiradas antes de actualizar.

Estos contenedores son entornos de desarrollo de clase con HTTP local. Un despliegue requiere HTTPS, configuración privada, servidores adecuados, protección contra abuso y revisión de las garantías de concurrencia de la base de datos. La presentación identifica TLS, Nginx y PostgreSQL como contexto de evolución. OAuth/OIDC y passkeys quedan para otra etapa.
