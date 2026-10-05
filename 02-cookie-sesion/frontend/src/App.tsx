import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError, clearCsrf, loadCsrf, sessionRequest } from './api'
import './App.css'

type Activity = { id: string; title: string; starts_at: string; capacity: number; available_slots: number }
type Enrollment = { id: string; activity_id: string; participant_id: string; enrolled_at: string }
type Profile = { id: string; name: string; email: string }

/** Agrupa datos del área privada; cada consulta envía la cookie de sesión. */
async function privateData() {
  const profile = await sessionRequest<Profile>('/api/v1/me')
  const [enrollments, activities] = await Promise.all([
    sessionRequest<Enrollment[]>('/api/v1/me/enrollments'),
    sessionRequest<Activity[]>('/api/v1/activities'),
  ])
  return { profile, enrollments, activities }
}

/** Renderiza el mismo recorrido de usuario con funciones exclusivamente de sesión Django. */
function App() {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [activities, setActivities] = useState<Activity[]>([])
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [page, setPage] = useState<'login' | 'register'>('login')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [restoring, setRestoring] = useState(true)

  useEffect(() => {
    let active = true
    /** Consulta /me con cookie antes de mostrar identidad; React no persiste perfiles. */
    async function restoreAccess() {
      try {
        const data = await privateData()
        if (active) {
          setProfile(data.profile)
          setEnrollments(data.enrollments)
          setActivities(data.activities)
        }
      } catch (error) {
        if (!active) return
        // Sin sesión es el estado inicial normal; red o servidor sí requieren aviso.
        if (!(error instanceof ApiError && error.status === 401)) {
          setMessage(error instanceof Error ? error.message : 'No se pudo restaurar el acceso.')
        }
      } finally { if (active) setRestoring(false) }
    }
    void restoreAccess()
    return () => { active = false }
  }, [])

  /** Limpia la interfaz y CSRF; la invalidación de sesión corresponde al servidor. */
  function forgetAccess() {
    clearCsrf()
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

  /** Inicia sesión con CSRF y luego actualiza el token que Django acaba de rotar. */
  async function signIn() {
    await sessionRequest<Profile>('/api/v1/auth/login', 'POST', { email, password })
    await loadCsrf()
    const data = await privateData()
    setProfile(data.profile)
    setEnrollments(data.enrollments)
    setActivities(data.activities)
    setPassword('')
  }

  /** Registra sin login implícito, elimina la contraseña del formulario y vuelve al ingreso. */
  async function register() {
    await sessionRequest<Profile>('/api/v1/auth/register', 'POST', { name, email, password })
    setPassword('')
    setName('')
    setPage('login')
    setMessage('Cuenta creada. Ahora podés ingresar.')
  }

  /** Pide invalidación remota y siempre limpia la interfaz, informando si no se confirmó. */
  async function signOut() {
    try {
      await sessionRequest<void>('/api/v1/auth/logout', 'POST')
      setMessage('Saliste de la aplicación. La sesión fue invalidada.')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setMessage('La sesión ya no estaba vigente.')
      } else {
        throw new Error('Se limpió la interfaz, pero no se confirmó la invalidación remota. La cookie HttpOnly podría restaurar acceso al recargar.')
      }
    } finally { forgetAccess() }
  }

  /** Ejecuta inscripción/cancelación y luego vuelve a consultar cupos e inscripciones. */
  async function changeEnrollment(path: string, method: 'PUT' | 'DELETE') {
    await sessionRequest<void>(path, method)
    const data = await privateData()
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
    <header><span className="eyebrow">Arquitecturas web · Autenticación</span><h1>Actividades e inscripciones</h1><p>Ejemplo 02 · Cookie de sesión</p></header>
    {message && <p role="status" className="notice">{message}</p>}
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
        <section><div className="row"><div><span className="eyebrow">Mi perfil</span><h2>{profile.name}</h2><p>{profile.email}</p></div><button className="secondary" disabled={busy} onClick={() => void act(signOut)}>Salir</button></div></section>
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
    <footer>Observá las peticiones en Network. La sesión viaja en una cookie HttpOnly; las escrituras incluyen X-CSRFToken obtenido de la API.</footer>
  </main>
}

export default App
