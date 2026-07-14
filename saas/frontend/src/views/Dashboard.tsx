import { useEffect, useState } from "react";
import { api, Job } from "../api";
import { relativeTime, Skeletons, StatusBadge } from "./shared";

// Live-polling job list with lifecycle badges and an empty state.
export function Dashboard({
  onOpenJob,
  onCompose,
}: {
  onOpenJob: (id: string) => void;
  onCompose: () => void;
}) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const list = await api.listJobs();
        if (alive) {
          setJobs(list.sort((a, b) => b.created_at.localeCompare(a.created_at)));
          setError(false);
        }
      } catch {
        if (alive) setError(true);
      }
    }
    refresh();
    const t = setInterval(refresh, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (jobs === null && !error) return <Skeletons />;

  if (error && jobs === null) {
    return <div className="alert alert-error">Couldn't load your jobs. We'll keep retrying.</div>;
  }

  if (jobs !== null && jobs.length === 0) {
    return (
      <div className="empty-state">
        <h2>No jobs yet</h2>
        <p>Train your first locomotion policy — pick an environment, tune the policy, and go.</p>
        <button className="btn" onClick={onCompose} style={{ marginTop: "var(--sp-4)" }}>
          Create your first job
        </button>
      </div>
    );
  }

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", marginBottom: "var(--sp-4)" }}>
        <h1 className="section-title" style={{ flex: 1, marginBottom: 0 }}>
          Jobs
        </h1>
        <button className="btn" onClick={onCompose}>
          New job
        </button>
      </div>
      {error && <div className="alert alert-error">Connection hiccup — showing the last known state.</div>}
      <div className="job-list">
        {jobs!.map((j) => (
          <button key={j.id} className="job-row" onClick={() => onOpenJob(j.id)}>
            {j.resolved_config.example?.avatar ? (
              <img className="job-row-avatar" src={j.resolved_config.example.avatar} alt="" />
            ) : (
              <span className="job-row-avatar fallback" aria-hidden>{j.job_kind === "custom-robot" ? "R" : "P"}</span>
            )}
            <div className="job-row-main">
              <div className="job-row-title">
                {j.job_kind === "custom-robot"
                  ? `${j.resolved_config.robot?.name ?? "Uploaded robot"} · ${j.resolved_config.setup?.task_template_id?.replace(/-/g, " ") ?? "Custom locomotion"}`
                  : j.resolved_config.example
                    ? `${j.resolved_config.example.label} · ${j.resolved_config.example.task}`
                  : `${j.environment} · ${j.algorithm}${j.preset ? ` · ${j.preset}` : ""}`}
              </div>
              <div className="job-row-sub">
                #{j.id.slice(0, 8)} · created {relativeTime(j.created_at)} · updated {relativeTime(j.updated_at)}
              </div>
            </div>
            <StatusBadge status={j.status} />
          </button>
        ))}
      </div>
    </>
  );
}
