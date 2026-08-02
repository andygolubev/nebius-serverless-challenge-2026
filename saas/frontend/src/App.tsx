import { useEffect, useState } from "react";
import { api, session, SESSION_EXPIRED_EVENT } from "./api";
import { About } from "./views/About";
import { Dashboard } from "./views/Dashboard";
import { JobDetail } from "./views/JobDetail";
import { Login } from "./views/Login";
import { MyRobots } from "./views/MyRobots";
import { Showcase, ShowcaseDetail } from "./views/Showcase";
import { Terms } from "./views/Terms";

// The showcase is the root view whether or not there is a session, so a visitor
// never meets a login wall before they have seen anything. Login is a destination
// reached deliberately, and a 401 returns here rather than stranding the user.
type Route =
  | { view: "showcase" }
  | { view: "showcase-example"; id: string }
  | { view: "about" }
  | { view: "terms" }
  | { view: "login" }
  | { view: "dashboard" }
  | { view: "robots" }
  | { view: "job"; id: string };

const PUBLIC_VIEWS = new Set<Route["view"]>(["showcase", "showcase-example", "about", "terms", "login"]);

export function App() {
  const [authed, setAuthed] = useState(() => session.token !== null);
  const [route, setRoute] = useState<Route>({ view: "showcase" });

  // Any 401 clears the stored session and returns to the public showcase.
  useEffect(() => {
    const onExpired = () => {
      setAuthed(false);
      setRoute({ view: "showcase" });
    };
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired);
  }, []);

  async function logout() {
    try {
      await api.logout();
    } catch {
      // revoking best-effort; clear locally regardless
    }
    session.clear();
    setAuthed(false);
    setRoute({ view: "showcase" });
  }

  // Signing in lands on My Robots: uploading and preparing your own robot is the
  // only way to create a training job.
  function afterLogin() {
    setAuthed(true);
    setRoute({ view: "robots" });
  }

  function trainYourOwn() {
    setRoute(authed ? { view: "robots" } : { view: "login" });
  }

  // An authenticated-only view reached without a session falls back to the showcase
  // rather than rendering a broken page.
  const active: Route = !authed && !PUBLIC_VIEWS.has(route.view) ? { view: "showcase" } : route;
  const routeKey = "id" in active ? `${active.view}:${active.id}` : active.view;

  useEffect(() => {
    document.documentElement.scrollTop = 0;
    document.body.scrollTop = 0;
  }, [routeKey]);

  return (
    <div className="shell">
      <header className="topbar">
        <button
          className="brand brand-button"
          onClick={() => setRoute({ view: "showcase" })}
          aria-label="Sim2Policy home"
        >
          <span className="brand-dot" aria-hidden />
          Sim2Policy
        </button>
        <nav aria-label="Main">
          <button
            className={`nav-btn ${active.view === "showcase" || active.view === "showcase-example" ? "active" : ""}`}
            onClick={() => setRoute({ view: "showcase" })}
          >
            Verified runs
          </button>
          {authed && (
            <>
              <button
                className={`nav-btn ${active.view === "dashboard" || active.view === "job" ? "active" : ""}`}
                onClick={() => setRoute({ view: "dashboard" })}
              >
                Jobs
              </button>
              <button
                className={`nav-btn ${active.view === "robots" ? "active" : ""}`}
                onClick={() => setRoute({ view: "robots" })}
              >
                My Robots
              </button>
            </>
          )}
        </nav>
        <span className="topbar-spacer" />
        {authed ? (
          <>
            <span className="user-chip" title={session.email ?? ""}>
              {session.email}
            </span>
            <button className="btn-ghost btn" onClick={logout}>
              Sign out
            </button>
          </>
        ) : (
          <button className="btn" onClick={() => setRoute({ view: "login" })}>
            Sign in
          </button>
        )}
      </header>

      <main className="content">
        {active.view === "showcase" && (
          <Showcase
            authed={authed}
            onSignIn={trainYourOwn}
            onOpenExample={(id) => setRoute({ view: "showcase-example", id })}
          />
        )}
        {active.view === "showcase-example" && (
          <ShowcaseDetail
            exampleId={active.id}
            authed={authed}
            onSignIn={trainYourOwn}
            onBack={() => setRoute({ view: "showcase" })}
          />
        )}
        {active.view === "about" && <About />}
        {active.view === "terms" && <Terms />}
        {active.view === "login" && (
          <Login onLogin={afterLogin} onCancel={() => setRoute({ view: "showcase" })} />
        )}
        {active.view === "dashboard" && (
          <Dashboard
            onOpenJob={(id) => setRoute({ view: "job", id })}
            onGetStarted={() => setRoute({ view: "robots" })}
            onBrowseShowcase={() => setRoute({ view: "showcase" })}
          />
        )}
        {active.view === "robots" && (
          <MyRobots
            onBrowseExamples={() => setRoute({ view: "showcase" })}
            onJobStarted={(id) => setRoute({ view: "job", id })}
          />
        )}
        {active.view === "job" && <JobDetail jobId={active.id} onBack={() => setRoute({ view: "dashboard" })} />}
      </main>

      <footer className={`site-footer${active.view === "terms" ? " terms-footer" : ""}`}>
        <div className="site-footer-inner">
          <span className="wordmark">Sim2Policy</span>
          <nav aria-label="Footer">
            <button type="button" onClick={() => setRoute({ view: "about" })}>About me</button>
            <button type="button" onClick={() => setRoute({ view: "terms" })}>Terms of use</button>
          </nav>
          <span className="meta">Nebius Serverless Challenge 2026</span>
        </div>
      </footer>
    </div>
  );
}
