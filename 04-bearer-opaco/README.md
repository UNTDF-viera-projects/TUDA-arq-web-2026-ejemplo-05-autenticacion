# 04 — Bearer opaco

API Django y frontend React independientes para estudiar un **token aleatorio revocable**. La persona registra una cuenta, ingresa, consulta perfil e inscripciones, se inscribe y cancela actividades. El código sólo implementa este mecanismo y el dominio de actividades.

[Presentación: bearer opaco](../autenticacion-seguridad-arquitecturas-web.html#opaco).

## Docker

Desde esta carpeta:

```sh
docker compose up --build
```

Frontend **http://localhost:5174**, API **http://localhost:8004**. No hace falta editar `.env`: los valores predeterminados migran y cargan datos idempotentes. El volumen propio `auth04-bearer-opaco_database` conserva SQLite; no comparte datos con otros ejemplos. Vite y Django son servidores de desarrollo.

Cuentas: `demo@example.com` y `other@example.com`, contraseña `Demo12345!`. El seed preserva contraseñas existentes y no duplica datos. También podés registrar una cuenta.

```sh
docker compose down
```

`down` conserva la base. Para cambiar configuración, copiar `.env.example` a `.env` y ajustar conjuntamente `FRONTEND_PORT`, `BACKEND_PORT`, `VITE_API_BASE_URL`, `CORS_ALLOWED_ORIGINS`. La API configurada para React usa `localhost`, nunca `backend:8000`: ese nombre sólo existe dentro de Docker. Si se cambia de host, actualizar CORS y `DJANGO_ALLOWED_HOSTS`.

## Local con uv

Requisitos: Python 3.12+, uv, Node 22.12+ y pnpm. Docker fija Python 3.12, uv 0.12.19 y pnpm 11.10.0. Ambos lockfiles bloquean dependencias.

Terminal backend:

```sh
cd backend
uv sync --frozen
uv run --frozen manage.py migrate
uv run --frozen manage.py seed_activities
uv run --frozen manage.py runserver localhost:8004
```

Terminal frontend:

```sh
cd frontend
pnpm install --frozen-lockfile
pnpm dev
```

La API local predeterminada es `http://localhost:8004`. `frontend/.env.local` puede cambiar `VITE_API_BASE_URL`. Vite usa puerto estricto: si está ocupado falla. No hay proxy `/api`.

## Workflow completo

1. **Registro:** React envía nombre, email y contraseña JSON a `/auth/register`. Django valida email y contraseña y crea usuario/participante en una transacción. Guarda la contraseña mediante el hasher Django; no emite token. La interfaz vuelve al ingreso.
2. **Ingreso:** `/auth/login` valida email/contraseña. Genera `secrets.token_urlsafe(32)`, guarda SHA-256, usuario, expiración y revocación, y entrega el secreto una vez en JSON `{token, token_type: "Bearer", expires_in: 3600}`. No crea cookie ni sesión.
3. **Persistencia:** React valida `/me`, guarda sólo el bearer en `sessionStorage`, clave `auth04_token`, y conserva una copia en memoria para headers. No guarda la contraseña ni un perfil persistido como prueba de identidad. Si el almacenamiento está bloqueado, explica el fallo y no presenta persistencia ficticia.
4. **Operaciones:** React envía `Authorization: Bearer <token>` y `credentials: 'omit'`. Django consulta el hash y comprueba usuario activo, vencimiento, revocación y participante. La identidad validada determina qué inscripciones pueden modificarse.
5. **Recarga:** lee la copia de la pestaña y valida `/me` antes de mostrar datos privados. Un `401` elimina token y estado privado y exige ingresar. Un `403` informa falta de permiso y conserva acceso.
6. **Expiración:** `OPAQUE_SECONDS=3600` por defecto. El siguiente request vencido obtiene `401`. No hay refresh; hay que volver a ingresar para emitir otro token.
7. **Salida:** `POST /auth/logout` revoca sólo el token presentado. La UI limpia almacenamiento, memoria y datos privados incluso si falla la conexión, y avisa si no se confirmó revocación remota. Otros tokens de la misma cuenta siguen vigentes. Borrar almacenamiento manualmente no revoca el servidor.

`sessionStorage` conserva datos durante recargas de una pestaña y es accesible a JavaScript: XSS puede robar el bearer. Una pestaña nueva suele tener otra área; duplicar pestañas, usar opener o restaurar sesiones del navegador puede copiar/restaurar datos. Cerrar la ventana no garantiza borrado seguro ni revocación remota. La persistencia limitada a pestaña sirve a este cliente con headers explícitos, no protege frente a XSS. Nunca se guardan secretos en URL, logs, código o `localStorage` indefinido.

Fuera de la práctica HTTP local se requiere HTTPS, configuración privada, defensas XSS, límites de intentos de login y un despliegue apropiado. SQLite y los servidores de desarrollo sirven a la clase; carga concurrente real requiere una base y manejo transaccional adecuados.

## CORS y CSRF

`localhost:5174` y `localhost:8004` son distintos **orígenes** porque cambia el puerto, pero siguen siendo el mismo sitio. No reproducen por sí solos sitios diferentes.

`django-cors-headers` permite exactamente `http://localhost:5174`, métodos GET/POST/PUT/DELETE/OPTIONS y headers Authorization/Content-Type. Atiende preflight sin autenticar y agrega CORS incluso sobre errores. No habilita credenciales CORS; React omite cookies. Una cookie de otra demo no autentica esta API.

El código agrega el bearer expresamente. El navegador no adjunta automáticamente una cookie de autenticación: por eso este flujo no usa tokens CSRF. CORS regula la lectura de respuestas en navegador y no bloquea clientes HTTP externos. Un bearer transportado en cookie tendría otras consideraciones CSRF.

## Endpoints

Prefijo `http://localhost:8004/api/v1`, sin barra final.

| Método y ruta | Acceso | Resultado |
| --- | --- | --- |
| GET `/activities` | Público | Catálogo y cupos |
| GET `/activities/{activity_id}` | Público | Actividad |
| POST `/auth/register` | JSON público | Cuenta y perfil, `201` |
| POST `/auth/login` | JSON público | Token, `200` |
| POST `/auth/logout` | Bearer | Revocación, `204` |
| GET `/me` | Bearer | Perfil `{id,name,email}` |
| GET `/me/enrollments` | Bearer | Inscripciones propias |
| PUT `/me/enrollments/{activity_id}` | Bearer, sin body | Nueva `201`; repetir `200` sin duplicar |
| DELETE `/me/enrollments/{activity_id}` | Bearer | Cancela sólo propia, idempotente `204` |
| DELETE `/enrollments/{enrollment_id}` | Bearer | Cancela por ID; ajena `403` |

Errores JSON `{code,message}`: `unauthorized` 401, `invalid_request` 400, `email_taken`/`capacity_exhausted` 409, `forbidden` 403 y recurso inexistente 404. No existen rutas de refresh, sesión, CSRF ni API key.

## Mapa del código

- [api_views.py](backend/activities/api_views.py): `digest`, `request_token`, `login_api`, `logout_api`, validación y autorización del dominio.
- [models.py](backend/activities/models.py): Activity, Participant, Enrollment, Token sin selector de tipo.
- [settings.py](backend/config/settings.py): CORS exacto y plazo, sin middleware de sesión.
- [auth.ts](frontend/src/auth.ts): `readToken`, `storeToken`, `clearToken`.
- [api.ts](frontend/src/api.ts): URL absoluta, header Bearer, cookies omitidas.
- [App.tsx](frontend/src/App.tsx): restauración, formularios, perfil e inscripciones.
- [tests.py](backend/activities/tests.py): pruebas exclusivas de opaco y dominio.
- [seed_activities.py](backend/activities/management/commands/seed_activities.py): carga repetible.

Todos los componentes y estilos son locales. Ningún import, build, volumen o función depende de otra carpeta.

## Recorrido y fallos en DevTools

1. Registrar: observar que no entrega token ni cookie. Ingresar: Network muestra `POST http://localhost:8004/api/v1/auth/login` y `/me`, con distinto puerto al frontend.
2. En Application → Session Storage → `http://localhost:5174`, observar `auth04_token`. No hay contraseña ni perfil persistido. No incluir secretos reales en capturas.
3. Recargar: `/me` valida antes de mostrar perfil; requests protegidos llevan Authorization y un preflight OPTIONS cuando corresponde.
4. Inscribirse: PUT sin body, actualización de lista/cupo. Repetir no duplica; cancelar restaura cupo.
5. En otro contexto de navegador ingresar con `other@example.com`. Copiar el **ID**, no el token, de una inscripción ajena y DELETE por ID usando el token propio: `403`. DELETE por actividad en `/me` no borra inscripciones ajenas.
6. Salir: POST logout, almacenamiento vacío y formulario. Reenviar el token revocado desde un cliente produce `401`.

Provocar: alterar `auth04_token` y recargar (401/limpieza), `OPAQUE_SECONDS=5` y esperar, llenar cupo (409), desactivar cuenta (401), bloquear almacenamiento o detener backend antes de salir (salida local con aviso de revocación no confirmada). Para probar CORS abrir UI desde `http://127.0.0.1:5174`: ese origen no está permitido. El servidor puede responder HTTP pero el navegador impide leer respuesta. `curl` no aplica CORS.

## Migraciones y bases existentes

0001–0003 quedan como historial. Antes de actualizar una base usada, detener backend y respaldar `backend/db.sqlite3` o el archivo del volumen. **0004 elimina ServiceKey, descarta tokens cuyo `kind` histórico no era `access`, conserva los access opacos y elimina `kind`.** No borra usuarios, actividades ni bases automáticamente. Datos de credenciales descartadas requieren respaldo para recuperarse.

La base nueva recorre ese historial y termina sólo con los modelos necesarios. Si decidís reiniciar expresamente todos los datos, `docker compose down --volumes` elimina cuentas, inscripciones y tokens de este volumen; el próximo arranque crea los datos de clase.

## Verificación

```sh
cd backend
uv run --frozen manage.py test
uv run --frozen manage.py check
uv run --frozen manage.py makemigrations --check --dry-run
```

```sh
cd frontend
pnpm build
pnpm lint
```

```sh
docker compose config --quiet
docker compose exec backend uv run --frozen manage.py test
```

Pruebas: hash, ausencia de cookies, expiración/revocación/inactividad, logout sólo de token actual, registro, rutas y credenciales ajenas, propiedad, cupos, idempotencia, CORS y seed. El navegador complementa las pruebas HTTP para validar CORS real.
