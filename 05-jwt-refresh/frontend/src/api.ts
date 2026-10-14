/** URL absoluta de la API: el navegador usa otro puerto, sin proxy Vite. */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8005"
).replace(/\/$/, "");

/** Error HTTP observable: 401 puede renovar, 403 conserva identidad y permisos. */
export class ApiError extends Error {
  /** Conserva estado HTTP y código sin exponer credenciales en el mensaje. */
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

// Ningún secreto se persiste en Web Storage. El refresh permanece inaccesible en una cookie.
let access = "";
let accessVersion = 0;
let csrfToken = "";
let csrfPending: Promise<string> | null = null;
let refreshPending: Promise<string> | null = null;

type TokenReply = {
  access: string;
  csrfToken: string;
  expires_in: number;
  token_type: "Bearer";
};

/** Ejecuta HTTP y conserva estados de error; nunca inicia refresh por sí mismo. */
async function request<T>(
  path: string,
  method: string,
  credentials: RequestCredentials,
  headers: Record<string, string> = {},
  body?: unknown,
): Promise<T> {
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      credentials,
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(
      "No se pudo contactar la API. Revisá la conexión y la configuración CORS.",
    );
  }
  if (!response.ok) {
    const details = (await response.json().catch(() => ({}))) as {
      code?: string;
      message?: string;
    };
    // Otra pestaña puede rotar CSRF. La próxima acción obtiene el token nuevo, sin
    // reintentar esta escritura ni tratar un 403 como cierre de identidad.
    if (response.status === 403 && details.code === "csrf_failed")
      csrfToken = "";
    throw new ApiError(
      response.status,
      details.code ?? "http_error",
      details.message ?? `Error HTTP ${response.status}`,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : (response.json() as Promise<T>);
}

/** Consulta catálogo o registra una cuenta sin enviar cookies ni access. */
export function publicRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  return request<T>(path, method, "omit", {}, body);
}

/** Obtiene CSRF por JSON y permite al navegador guardar su cookie HttpOnly. */
export async function loadCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  // Comparte una obtención pendiente entre efectos o requests concurrentes.
  if (!csrfPending) {
    csrfPending = request<{ csrfToken: string }>(
      "/api/v1/auth/csrf",
      "GET",
      "include",
    )
      .then((reply) => {
        csrfToken = reply.csrfToken;
        return csrfToken;
      })
      .finally(() => {
        csrfPending = null;
      });
  }
  return csrfPending;
}

/** Olvida solo el access y CSRF en memoria; no puede borrar una cookie HttpOnly. */
export function clearAccess() {
  access = "";
  csrfToken = "";
  accessVersion++;
}

/** Indica si hay access en memoria, sin usarlo como prueba de identidad del servidor. */
export function hasAccess(): boolean {
  return Boolean(access);
}

/** Valida login con CSRF y actualiza el token CSRF que el servidor acaba de rotar. */
export async function login(email: string, password: string): Promise<void> {
  const token = await loadCsrf();
  const reply = await request<TokenReply>(
    "/api/v1/auth/login",
    "POST",
    "include",
    { "X-CSRFToken": token },
    { email, password },
  );
  access = reply.access;
  accessVersion++;
  csrfToken = reply.csrfToken;
}

/** Renueva como máximo una vez en paralelo, incluso durante StrictMode de React. */
export function refreshAccess(): Promise<string> {
  if (!refreshPending) {
    refreshPending = (async () => {
      try {
        const token = await loadCsrf();
        const reply = await request<TokenReply>(
          "/api/v1/auth/refresh",
          "POST",
          "include",
          { "X-CSRFToken": token },
        );
        access = reply.access;
        accessVersion++;
        csrfToken = reply.csrfToken;
        return access;
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 403)) clearAccess();
        throw error;
      }
    })().finally(() => {
      refreshPending = null;
    });
  }
  return refreshPending;
}

/** Envía Bearer explícito sin cookies; ante 401 renueva y reintenta una única vez. */
export async function accessRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const credential = access || (await refreshAccess());
  const version = accessVersion;
  try {
    return await request<T>(
      path,
      method,
      "omit",
      { Authorization: `Bearer ${credential}` },
      body,
    );
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401) throw error;
    // Otro request puede haber renovado mientras éste recibía el 401. Comparamos
    // versiones: dos JWT emitidos en el mismo segundo pueden tener idéntico texto.
    const renewed =
      access && accessVersion !== version ? access : await refreshAccess();
    try {
      return await request<T>(
        path,
        method,
        "omit",
        { Authorization: `Bearer ${renewed}` },
        body,
      );
    } catch (retryError) {
      if (retryError instanceof ApiError && retryError.status === 401)
        clearAccess();
      throw retryError;
    }
  }
}

/** Invalida refresh en servidor y limpia memoria aun cuando falla la comunicación. */
export async function logout(): Promise<void> {
  try {
    const token = await loadCsrf();
    await request<void>("/api/v1/auth/logout", "POST", "include", {
      "X-CSRFToken": token,
    });
  } finally {
    clearAccess();
  }
}
