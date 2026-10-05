/** Persistencia de la SPA Basic: Base64 contiene la contraseña y JavaScript puede leerla. */
const STORAGE_KEY = 'auth03_basic'
export type StoredCredential = { value: string; warning: string }

/** Codifica UTF-8; Base64 es reversible y no protege el secreto ante XSS. */
export function encodeCredential(email: string, password: string): string {
  const bytes = new TextEncoder().encode(`${email.trim().toLowerCase()}:${password}`)
  return btoa(Array.from(bytes, byte => String.fromCharCode(byte)).join(''))
}

/** Lee el valor de la pestaña sin darlo por válido: /me debe verificarlo luego. */
export function readCredential(): StoredCredential {
  try { return { value: sessionStorage.getItem(STORAGE_KEY) ?? '', warning: '' } }
  catch { return { value: '', warning: 'El navegador bloqueó sessionStorage. Podés ingresar, pero no restaurar el acceso al recargar.' } }
}

/** Guarda solo una credencial validada. Si falla storage, el acceso continúa en memoria. */
export function saveCredential(value: string): string {
  try { sessionStorage.setItem(STORAGE_KEY, value); return '' }
  catch { return 'No se pudo guardar en sessionStorage. El acceso se conservará solo mientras esta página esté abierta.' }
}

/** Borra la copia de la pestaña. La salida local nunca cambia la contraseña del servidor. */
export function clearCredential(): string {
  try { sessionStorage.removeItem(STORAGE_KEY); return '' }
  catch { return 'No se pudo limpiar sessionStorage. Cerrá la pestaña y borrá sus datos de almacenamiento; una copia guardada podría restaurar acceso.' }
}
