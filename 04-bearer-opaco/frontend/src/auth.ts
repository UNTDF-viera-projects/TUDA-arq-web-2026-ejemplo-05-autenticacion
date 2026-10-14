const TOKEN_KEY = 'auth04_token'

/** Recupera el token de esta pestaña. Todavía debe validarse con /me. */
export function readToken(): string {
  try { return sessionStorage.getItem(TOKEN_KEY) ?? '' } catch {
    throw new Error('No se pudo leer el almacenamiento de la pestaña. Revisá los permisos del navegador.')
  }
}

/** Persiste sólo el bearer opaco, nunca contraseña ni un perfil como identidad. */
export function storeToken(token: string): void {
  try { sessionStorage.setItem(TOKEN_KEY, token) } catch {
    throw new Error('No se pudo guardar el token. Habilitá el almacenamiento de esta pestaña para conservar el acceso.')
  }
}

/** Borra la copia del navegador; la revocación remota se realiza por separado. */
export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_KEY)
}
