import { useEffect, useState, type FormEvent } from "react";
import { ApiError, requestApi } from "./api";
import { clearToken, readToken, storeToken } from "./auth";
import "./App.css";

type Profile = { id: string; name: string; email: string };
type Activity = {
  id: string;
  title: string;
  starts_at: string;
  capacity: number;
  available_slots: number;
};
type Enrollment = {
  id: string;
  activity_id: string;
  participant_id: string;
  enrolled_at: string;
};

/** Convierte errores de red, HTTP o almacenamiento en un mensaje para la persona. */
function messageFor(error: unknown): string {
  if (error instanceof TypeError)
    return "No se pudo conectar con la API. Revisá la conexión y el origen permitido por CORS.";
  return error instanceof Error
    ? error.message
    : "No pudimos completar la operación.";
}

/** Interfaz exclusiva del bearer opaco: no utiliza cookies, refresh ni otros mecanismos. */
export default function App() {
  const [screen, setScreen] = useState<"login" | "register">("login");
  const [token, setToken] = useState("");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  /** Borra todos los datos privados incluso si el navegador bloquea sessionStorage. */
  function forgetSession(): string {
    setToken("");
    setProfile(null);
    setEnrollments([]);
    setActivities([]);
    try {
      clearToken();
      return "";
    } catch {
      return "El navegador impidió borrar el almacenamiento. Borrá los datos del sitio para retirar esa copia.";
    }
  }

  /** Un 401 invalida la copia local; un 403 conserva el acceso y explica el permiso. */
  function reportError(error: unknown) {
    const cleanup =
      error instanceof ApiError && error.status === 401 ? forgetSession() : "";
    setMessage([messageFor(error), cleanup].filter(Boolean).join(" "));
  }

  useEffect(() => {
    let active = true;
    /** La recarga lee el token, valida /me y recién entonces muestra datos privados. */
    async function restoreSession() {
      try {
        const saved = readToken();
        if (saved) {
          const user = await requestApi<Profile>("/me", saved);
          const [catalog, mine] = await Promise.all([
            requestApi<Activity[]>("/activities"),
            requestApi<Enrollment[]>("/me/enrollments", saved),
          ]);
          if (active) {
            setToken(saved);
            setProfile(user);
            setActivities(catalog);
            setEnrollments(mine);
          }
        }
      } catch (error) {
        if (active) {
          let cleanup = "";
          if (error instanceof ApiError && error.status === 401) {
            try {
              clearToken();
            } catch {
              cleanup = " No se pudo borrar el almacenamiento del navegador.";
            }
          }
          setMessage(messageFor(error) + cleanup);
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void restoreSession();
    return () => {
      active = false;
    };
  }, []);

  /** Actualiza listas después de una inscripción o cancelación confirmada por la API. */
  async function reloadData(value: string) {
    const [catalog, mine] = await Promise.all([
      requestApi<Activity[]>("/activities"),
      requestApi<Enrollment[]>("/me/enrollments", value),
    ]);
    setActivities(catalog);
    setEnrollments(mine);
  }

  /** Obtiene un token, verifica perfil y sólo guarda una credencial que funciona. */
  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    let issued = "";
    try {
      const result = await requestApi<{ token: string }>("/auth/login", "", {
        method: "POST",
        body: JSON.stringify({
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      issued = result.token;
      const user = await requestApi<Profile>("/me", issued);
      // Si el almacenamiento está bloqueado, no fingimos persistencia tras recargar.
      storeToken(issued);
      await reloadData(issued);
      setToken(issued);
      setProfile(user);
      event.currentTarget?.reset();
    } catch (error) {
      if (issued) {
        try {
          await requestApi("/auth/logout", issued, { method: "POST" });
        } catch {
          /* El token mantiene su expiración si falla esta limpieza remota. */
        }
        forgetSession();
      }
      reportError(error);
    } finally {
      setBusy(false);
    }
  }

  /** Crea una cuenta; vuelve al ingreso sin emitir ni almacenar un token. */
  async function register(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      await requestApi("/auth/register", "", {
        method: "POST",
        body: JSON.stringify({
          name: form.get("name"),
          email: form.get("email"),
          password: form.get("password"),
        }),
      });
      setScreen("login");
      setMessage("Cuenta creada. Ya podés ingresar.");
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  }

  /** Revoca el token actual y limpia la copia local aunque haya un error de conexión. */
  async function logout() {
    setBusy(true);
    setMessage("");
    let warning = "";
    try {
      await requestApi("/auth/logout", token, { method: "POST" });
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) {
        warning =
          "Saliste de esta interfaz, pero no se confirmó la revocación remota. El token podría seguir válido hasta vencer.";
      }
    } finally {
      setMessage([warning, forgetSession()].filter(Boolean).join(" "));
      setBusy(false);
    }
  }

  /** La API decide propiedad y cupos; la UI bloquea envíos duplicados mientras espera. */
  async function changeEnrollment(
    activityId: string,
    method: "PUT" | "DELETE",
  ) {
    setBusy(true);
    setMessage("");
    try {
      await requestApi(`/me/enrollments/${activityId}`, token, { method });
      await reloadData(token);
      setMessage(
        method === "PUT" ? "Inscripción realizada." : "Inscripción cancelada.",
      );
    } catch (error) {
      reportError(error);
    } finally {
      setBusy(false);
    }
  }

  const myActivities = new Set(enrollments.map((item) => item.activity_id));
  return (
    <main className="shell">
      <header className="page-header">
        <p className="eyebrow">ARQUITECTURAS WEB · EJEMPLO 04</p>
        <h1>Actividades e inscripciones</h1>
        <p>Autenticación con bearer opaco</p>
      </header>
      {message && (
        <p className="notice" role="status">
          {message}
        </p>
      )}
      {loading ? (
        <section className="card">
          <p>Comprobando acceso…</p>
        </section>
      ) : !profile ? (
        <section className="card auth-card">
          <h2>{screen === "login" ? "Ingresar" : "Crear cuenta"}</h2>
          <form key={screen} onSubmit={screen === "login" ? login : register}>
            {screen === "register" && (
              <label>
                Nombre
                <input
                  name="name"
                  autoComplete="name"
                  maxLength={160}
                  required
                  disabled={busy}
                />
              </label>
            )}
            <label>
              Email
              <input
                name="email"
                type="email"
                autoComplete="username"
                maxLength={150}
                required
                disabled={busy}
              />
            </label>
            <label>
              Contraseña
              <input
                name="password"
                type="password"
                autoComplete={
                  screen === "login" ? "current-password" : "new-password"
                }
                minLength={screen === "register" ? 8 : undefined}
                required
                disabled={busy}
              />
            </label>
            <button disabled={busy}>
              {busy
                ? "Esperá…"
                : screen === "login"
                  ? "Ingresar"
                  : "Crear cuenta"}
            </button>
          </form>
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              setScreen(screen === "login" ? "register" : "login");
              setMessage("");
            }}
          >
            {screen === "login" ? "Crear cuenta" : "Volver al ingreso"}
          </button>
        </section>
      ) : (
        <>
          <section className="card profile">
            <div>
              <p className="eyebrow">TU PERFIL</p>
              <h2>{profile.name}</h2>
              <p>{profile.email}</p>
            </div>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => void logout()}
            >
              Salir
            </button>
          </section>
          <div className="dashboard">
            <section className="card">
              <h2>Mis inscripciones</h2>
              {!enrollments.length && (
                <p className="muted">Todavía no tenés inscripciones.</p>
              )}
              <ul className="activity-list">
                {enrollments.map((item) => {
                  const activity = activities.find(
                    (row) => row.id === item.activity_id,
                  );
                  return (
                    <li key={item.id}>
                      <h3>{activity?.title ?? "Actividad"}</h3>
                      <p>
                        {activity
                          ? new Date(activity.starts_at).toLocaleString("es-AR")
                          : ""}
                      </p>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          void changeEnrollment(item.activity_id, "DELETE")
                        }
                      >
                        Cancelar inscripción
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
            <section className="card">
              <h2>Actividades disponibles</h2>
              {!activities.length && (
                <p className="muted">No hay actividades publicadas.</p>
              )}
              <ul className="activity-list">
                {activities.map((activity) => (
                  <li key={activity.id}>
                    <h3>{activity.title}</h3>
                    <p>
                      {new Date(activity.starts_at).toLocaleString("es-AR")}
                    </p>
                    <p className="muted">
                      {activity.available_slots} de {activity.capacity} cupos
                      disponibles
                    </p>
                    <button
                      disabled={
                        busy ||
                        myActivities.has(activity.id) ||
                        activity.available_slots === 0
                      }
                      onClick={() => void changeEnrollment(activity.id, "PUT")}
                    >
                      {myActivities.has(activity.id)
                        ? "Ya estás inscripto/a"
                        : activity.available_slots === 0
                          ? "Sin cupos"
                          : "Inscribirme"}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
