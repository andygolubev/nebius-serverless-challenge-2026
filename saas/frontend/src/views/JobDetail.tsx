import { useEffect, useState } from "react";
import { api, ArtifactManifest, Job, TERMINAL } from "../api";
import { LifecycleTimeline, relativeTime, StatusBadge } from "./shared";

// Resolved configuration, live lifecycle, and results once the job completes.
export function JobDetail({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactManifest | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const j = await api.getJob(jobId);
        if (!alive) return;
        setJob(j);
        setError(null);
        if (j.status === "completed") {
          try {
            const m = await api.getArtifacts(jobId);
            if (alive) setArtifacts(m);
          } catch {
            // 409 while artifacts settle; next poll picks them up
          }
        }
      } catch {
        if (alive) setError("Couldn't load this job. It may have been removed.");
      }
    }
    refresh();
    const t = setInterval(() => {
      if (job && TERMINAL.has(job.status) && (job.status !== "completed" || artifacts)) return;
      refresh();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, job?.status, artifacts !== null]);

  if (error) {
    return (
      <>
        <button className="btn-link" onClick={onBack}>
          ← Back to jobs
        </button>
        <div className="alert alert-error">{error}</div>
      </>
    );
  }

  if (!job) {
    return <div className="skeleton" style={{ height: "12rem" }} aria-label="Loading job" />;
  }

  return (
    <>
      <button className="btn-link" onClick={onBack}>
        ← Back to jobs
      </button>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--sp-3)", margin: "var(--sp-3) 0" }}>
        <h1 className="section-title" style={{ flex: 1, marginBottom: 0 }}>
          {job.environment} · {job.algorithm}
        </h1>
        <StatusBadge status={job.status} />
      </div>
      <p className="section-sub">
        #{job.id.slice(0, 8)} · created {relativeTime(job.created_at)} · updated {relativeTime(job.updated_at)}
      </p>

      <LifecycleTimeline status={job.status} />

      <div className="card" style={{ margin: "var(--sp-4) 0" }}>
        <h2 style={{ fontSize: "var(--fs-md)", marginBottom: "var(--sp-3)" }}>Configuration</h2>
        <dl className="kv">
          {job.preset && (
            <>
              <dt>preset</dt>
              <dd>{job.preset}</dd>
            </>
          )}
          <dt>environment</dt>
          <dd>{job.resolved_config.environment}</dd>
          <dt>algorithm</dt>
          <dd>{job.resolved_config.algorithm}</dd>
          {Object.entries(job.resolved_config.params).map(([k, v]) => (
            <span key={k} style={{ display: "contents" }}>
              <dt>{k}</dt>
              <dd>{String(v)}</dd>
            </span>
          ))}
        </dl>
      </div>

      {job.status === "completed" && (
        <div className="card">
          <h2 style={{ fontSize: "var(--fs-md)", marginBottom: "var(--sp-3)" }}>Results</h2>
          {!artifacts ? (
            <div className="skeleton" style={{ height: "5rem" }} aria-label="Loading results" />
          ) : (
            <>
              <div className="metrics-grid" style={{ marginBottom: "var(--sp-4)" }}>
                {Object.entries(artifacts.metrics).map(([k, v]) => (
                  <div className="metric" key={k}>
                    <div className="label">{k}</div>
                    <div className="value">{String(v)}</div>
                  </div>
                ))}
              </div>
              {artifacts.media.length > 0 && (
                <>
                  <h3 style={{ fontSize: "var(--fs-sm)", marginBottom: "var(--sp-2)" }}>Media</h3>
                  <ul style={{ margin: 0, paddingLeft: "1.2rem", fontSize: "var(--fs-sm)", wordBreak: "break-all" }}>
                    {artifacts.media.map((m) => (
                      <li key={m}>
                        <a href={m} target="_blank" rel="noreferrer">
                          {m}
                        </a>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </div>
      )}

      {job.status === "failed" && (
        <div className="alert alert-error">This job failed. Check the run logs on the server for details.</div>
      )}
    </>
  );
}
