export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8004"
).replace(/\/$/, "");

/** Error HTTP con su estado; 401 exige borrar el token, 403 indica autorización. */
export class ApiError extends Error {
  status: number;
  /** Conserva el estado HTTP para distinguir autenticación de autorización. */
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** Llama directamente al otro origen y agrega Bearer sólo cuando se pide. */
export async function requestApi<T>(
  path: string,
  token = "",
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_BASE_URL}/api/v1${path}`, {
    ...options,
    headers,
    credentials: "omit",
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      body.message ?? `Error HTTP ${response.status}`,
      response.status,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
