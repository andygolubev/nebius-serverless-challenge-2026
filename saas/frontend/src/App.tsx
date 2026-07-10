import { useEffect, useState } from "react";
import { api, session, SESSION_EXPIRED_EVENT } from "./api";
import { Composer } from "./views/Composer";
import { Dashboard } from "./views/Dashboard";
import { JobDetail } from "./views/JobDetail";
import { Login } from "./views/Login";

type Route = { view: "dashboard" } | { view: "composer" } | { view: "job"; id: string };

export function App() {
  const [authed, setAuthed] = useState(() => session.token !== null);
  const [route, setRoute] = useState<Route>({ view: "dashboard" });

  // Any 401 clears the stored session and drops back to login.
  useEffect(() => {
    const onExpired = () => {
      setAuthed(false);
      setRoute({ view: "dashboard" });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  if (!authed) {
    return <Login onLogin={() => setAuthed(true)} />;
  }

  async function logout() {
    try {
      await api.logout();
    } catch {
      // revoking best-effort; clear locally regardless
    }
    session.clear();
    setAuthed(false);
    setRoute({ view: "dashboard" });
  }

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          <span className="brand-dot" aria-hidden />
          Sim2Policy
        </span>
        <nav aria-label="Main">
          <button
            className={`nav-btn ${route.view !== "composer" ? "active" : ""}`}
            onClick={() => setRoute({ view: "dashboard" })}
          >
            Jobs
          </button>
          <button
            className={`nav-btn ${route.view === "composer" ? "active" : ""}`}
            onClick={() => setRoute({ view: "composer" })}
          >
            New job
          </button>
        </nav>
        <span className="topbar-spacer" />
        <span className="user-chip" title={session.email ?? ""}>
          {session.email}
        </span>
        <button className="btn-ghost btn" onClick={logout}>
          Sign out
        </button>
      </header>

      <main className="content">
        {route.view === "dashboard" && (
          <Dashboard
            onOpenJob={(id) => setRoute({ view: "job", id })}
            onCompose={() => setRoute({ view: "composer" })}
          />
        )}
        {route.view === "composer" && <Composer onSubmitted={() => setRoute({ view: "dashboard" })} />}
        {route.view === "job" && <JobDetail jobId={route.id} onBack={() => setRoute({ view: "dashboard" })} />}
      </main>
    </div>
  );
}
