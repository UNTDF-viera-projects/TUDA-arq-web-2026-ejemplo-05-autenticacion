import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, basicRequest } from './api'
import { clearCredential, encodeCredential, readCredential, saveCredential } from './credential'
import './App.css'

type Activity = { id: string; title: string; starts_at: string; capacity: number; available_slots: number }
type Enrollment = { id: string; activity_id: string; participant_id: string; enrolled_at: string }
type Profile = { id: string; name: string; email: string }

/** Agrupa datos del área privada; cada consulta envía y verifica Basic nuevamente. */
async function privateData(value: string) {
  const profile = await basicRequest<Profile>('/api/v1/me', value)
  const [enrollments, activities] = await Promise.all([
    basicRequest<Enrollment[]>('/api/v1/me/enrollments', value),
    basicRequest<Activity[]>('/api/v1/activities'),
  ])
  return { profile, enrollments, activities }
}

/** Renderiza el mismo recorrido de usuario con funciones exclusivamente de Basic. */
function App() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [credential, setCredential] = useState('')
  const [activities, setActivities] = useState<Activity[]>([])
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [page, setPage] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [warning, setWarning] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    let active = true
    /** Restaura únicamente después de /me: storage no demuestra autenticación. */
    async function restoreAccess() {
      const stored = readCredential()
      if (active) setWarning(stored.warning)
      try {
        if (stored.value) {
          const data = await privateData(stored.value)
          if (active) {
            setCredential(stored.value)
            setProfile(data.profile)
            setEnrollments(data.enrollments)
            setActivities(data.activities)
          }
        }
      } catch (error) {
        if (!active) return
        if (error instanceof ApiError && error.status === 401) setWarning(clearCredential())
        setMessage(error instanceof Error ? error.message : 'No se pudo restaurar el acceso.')
      } finally {
        if (active) setRestoring(false)
      }
    }
    void restoreAccess()
    return () => { active = false }
  }, [])

  /** Limpia datos privados incluso si el almacenamiento está bloqueado. */
  function forgetAccess() {
    setWarning(clearCredential())
    setCredential('')
    setProfile(null)
    setEnrollments([])
    setActivities([])
    setPassword('')
    setPage('login')
  }

  /** Serializa acciones, muestra errores y distingue 401 de 403 sin cerrar por permisos. */
  async function act(job: () => Promise<void>) {
    setBusy(true)
    setMessage('')
    try { await job() }
    catch (error) {
      if (error instanceof ApiError && error.status === 401) forgetAccess()
      setMessage(error instanceof Error ? error.message : 'Error desconocido.')
    } finally { setBusy(false) }
  }

  /** Valida Basic en /me antes de guardar; una contraseña fallida jamás se persiste. */
  async function signIn() {
    const value = encodeCredential(email, password)
    const data = await privateData(value)
    setWarning(saveCredential(value))
    setCredential(value)
    setProfile(data.profile)
    setEnrollments(data.enrollments)
    setActivities(data.activities)
    setPassword('')
  }

  /** Registra sin login implícito, elimina la contraseña del formulario y vuelve al ingreso. */
  async function register() {
    await basicRequest<Profile>('/api/v1/auth/register', '', 'POST', { name, email, password })
    setPassword('')
    setName('')
    setPage('login')
    setMessage('Cuenta creada. Ahora podés ingresar.')
  }

  /** Salir es local: no existe endpoint logout ni credencial remota revocable en Basic. */
  function signOut() {
    forgetAccess()
    setMessage('Saliste de la aplicación. La contraseña sigue siendo válida en el servidor.')
  }

  /** Ejecuta inscripción/cancelación y luego vuelve a consultar cupos e inscripciones. */
  async function changeEnrollment(path: string, method: 'PUT' | 'DELETE') {
    await basicRequest<void>(path, credential, method)
    const data = await privateData(credential)
    setProfile(data.profile)
    setEnrollments(data.enrollments)
    setActivities(data.activities)
    setMessage(method === 'PUT' ? 'Inscripción realizada.' : 'Inscripción cancelada.')
  }

  /** Conserva submit con teclado y evita el envío convencional del formulario. */
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void act(page === 'login' ? signIn : register)
  }

  /** Cambia de formulario sin arrastrar la contraseña o un mensaje anterior. */
  function switchPage() {
    setPage(page === 'login' ? 'register' : 'login')
    setPassword('')
    setMessage('')
  }

  return <main>
    <header><span className="eyebrow">Arquitecturas web · Autenticación</span><h1>Actividades e inscripciones</h1><p>Ejemplo 03 · HTTP Basic</p></header>
    {message && <p role="status" className="notice">{message}</p>}
    {warning && <p role="alert" className="notice">{warning}</p>}
    {restoring ? <section aria-busy="true"><p>Comprobando acceso…</p></section> : !profile ?
      <section className="auth-card"><h2>{page === 'login' ? 'Ingresar' : 'Crear cuenta'}</h2>
        <p>{page === 'login' ? 'Ingresá para consultar tus inscripciones.' : 'Completá tus datos y después ingresá.'}</p>
        <form onSubmit={submit} className="form">
          {page === 'register' && <label>Nombre<input value={name} onChange={event => setName(event.target.value)} autoComplete="name" required maxLength={160} disabled={busy} /></label>}
          <label>Email<input value={email} onChange={event => setEmail(event.target.value)} type="email" autoComplete="username" required maxLength={150} disabled={busy} /></label>
          <label>Contraseña<input value={password} onChange={event => setPassword(event.target.value)} type="password" autoComplete={page === 'login' ? 'current-password' : 'new-password'} required minLength={page === 'register' ? 8 : undefined} disabled={busy} /></label>
          <button disabled={busy} type="submit">{busy ? 'Procesando…' : page === 'login' ? 'Ingresar' : 'Crear cuenta'}</button>
        </form>
        <button className="link-button" disabled={busy} onClick={switchPage}>{page === 'login' ? 'Crear cuenta' : 'Volver al ingreso'}</button>
      </section> : <>
        <section><div className="row"><div><span className="eyebrow">Mi perfil</span><h2>{profile.name}</h2><p>{profile.email}</p></div><button className="secondary" disabled={busy} onClick={signOut}>Salir</button></div></section>
        <div className="dashboard">
          <section aria-busy={busy}><h2>Mis inscripciones</h2>{enrollments.length === 0 ? <p>No tenés inscripciones todavía.</p> : <ul className="cards">{enrollments.map(enrollment => <li key={enrollment.id}>
            <strong>{activities.find(activity => activity.id === enrollment.activity_id)?.title ?? enrollment.activity_id}</strong>
            <small>Inscripción: {enrollment.id}</small>
            <div className="actions"><button className="secondary" disabled={busy} onClick={() => void act(() => changeEnrollment(`/api/v1/me/enrollments/${enrollment.activity_id}`, 'DELETE'))}>Cancelar</button><button className="link-button" disabled={busy} onClick={() => void act(() => changeEnrollment(`/api/v1/enrollments/${enrollment.id}`, 'DELETE'))}>Cancelar por ID</button></div>
          </li>)}</ul>}</section>
          <section aria-busy={busy}><h2>Actividades disponibles</h2>{activities.length === 0 ? <p>No hay actividades publicadas.</p> : <ul className="cards">{activities.map(activity => {
            const enrolled = enrollments.some(enrollment => enrollment.activity_id === activity.id)
            return <li key={activity.id}><strong>{activity.title}</strong><small>{new Date(activity.starts_at).toLocaleString('es-AR')}</small><span>{activity.available_slots} de {activity.capacity} cupos disponibles</span><button disabled={busy || enrolled || activity.available_slots === 0} onClick={() => void act(() => changeEnrollment(`/api/v1/me/enrollments/${activity.id}`, 'PUT'))}>{enrolled ? 'Ya estás inscripto/a' : activity.available_slots === 0 ? 'Sin cupo' : 'Inscribirme'}</button></li>
          })}</ul>}</section>
        </div>
      </>}
    <footer>Observá las peticiones en Network. La credencial Basic se conserva en sessionStorage de esta pestaña; Base64 es reversible y está expuesta ante XSS.</footer>
  </main>
}

export default App
