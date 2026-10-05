/** API exclusiva de Basic. Todas las llamadas usan otro origen y omiten cookies. */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8003').replace(/\/$/, '')

/** Error HTTP: 401 elimina acceso; 403 conserva identidad y muestra falta de permiso. */
export class ApiError extends Error {
  /** Guarda código y estado para distinguir credenciales inválidas de falta de permiso. */
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

/** Envía explícitamente Basic cuando hay credencial; no crea ni renueva tokens. */
export async function basicRequest<T>(path: string, credential = '', method = 'GET', body?: unknown): Promise<T> {
  const headers: Record<string, string> = {}
  if (credential) headers.Authorization = `Basic ${credential}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method, headers, credentials: 'omit', cache: 'no-store',
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new Error('No se pudo contactar la API. Revisá la conexión y la configuración CORS.')
  }
  if (!response.ok) {
    const details = await response.json().catch(() => ({})) as { code?: string; message?: string }
    throw new ApiError(response.status, details.code ?? 'http_error', details.message ?? `Error HTTP ${response.status}`)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}
