/** API de sesión: el navegador envía cookies; React administra solo el token CSRF. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8002').replace(/\/$/, '')
let csrfToken = ''

/** Conserva el estado HTTP para distinguir sesión vencida de CSRF/propiedad. */
export class ApiError extends Error {
  /** Guarda código y estado para decidir cómo mostrar el fallo de sesión o CSRF. */
  constructor(public status: number, public code: string, message: string) { super(message) }
}

/** Contacta otro origen con cookies y traduce errores de red o HTTP para la interfaz. */
async function fetchJson<T>(path: string, method = 'GET', headers: Record<string, string> = {}, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method, headers, credentials: 'include', cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch { throw new Error('No se pudo contactar la API. Revisá la conexión y la configuración CORS.') }
  if (!response.ok) {
    const details = await response.json().catch(() => ({})) as { code?: string; message?: string }
    throw new ApiError(response.status, details.code ?? 'http_error', details.message ?? `Error HTTP ${response.status}`)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

/** Obtiene CSRF desde JSON, incluso después del login que rota el secreto. */
export async function loadCsrf(): Promise<void> {
  const data = await fetchJson<{ csrfToken: string }>('/api/v1/auth/csrf')
  csrfToken = data.csrfToken
}

/** Borra únicamente el token CSRF en memoria; JavaScript no puede borrar sesión HttpOnly. */
export function clearCsrf(): void { csrfToken = '' }

/** Adjunta X-CSRFToken a registro/login/logout y escrituras, manteniendo credentials include. */
export async function sessionRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (!csrfToken) await loadCsrf()
    headers['X-CSRFToken'] = csrfToken
  }
  try { return await fetchJson<T>(path, method, headers, body) }
  catch (error) {
    // Otra pestaña puede rotar CSRF. Mostramos el 403 y pedimos un token nuevo
    // en la próxima acción, sin cerrar sesión ni repetir una escritura automáticamente.
    if (error instanceof ApiError && error.status === 403 && error.code === 'csrf_failed') clearCsrf()
    throw error
  }
}
