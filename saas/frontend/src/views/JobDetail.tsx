import { useEffect, useState } from "react";
import { api, ArtifactManifest, Job, TERMINAL } from "../api";
import { LifecycleTimeline, relativeTime, StatusBadge } from "./shared";

// Resolved configuration, live lifecycle, and results once the job completes.
export function JobDetail({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

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
            if (alive) {
              setArtifacts(m);
              const videos = m.artifacts.filter((a) => a.kind === "video");
              const final = videos.find((a) => a.id.toLowerCase().includes("final")) ?? videos[0];
              setSelectedVideo((current) => current ?? final?.id ?? null);
            }
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

      {job.status === "finalizing" && (
        <div className="alert">GPU training finished. Reports and playable media are being finalized.</div>
      )}

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
                    <pre className="value" style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{displayMetric(v)}</pre>
                  </div>
                ))}
              </div>
              {artifacts.artifacts.some((a) => a.kind === "video") && (
                <>
                  <h3 style={{ fontSize: "var(--fs-sm)", marginBottom: "var(--sp-2)" }}>Media</h3>
                  {artifacts.artifacts.filter((a) => a.kind === "video" && a.id === selectedVideo).map((a) => (
                    <div key={a.id}>
                      <video controls preload="metadata" style={{ width: "100%", maxHeight: "32rem", background: "#000" }} src={a.url}>
                        Your browser does not support HTML5 video.
                      </video>
                      <p><a href={a.url} target="_blank" rel="noreferrer">Open</a> · <a href={a.download_url}>Download</a></p>
                    </div>
                  ))}
                  <div className="env-grid" role="radiogroup" aria-label="Select video">
                    {artifacts.artifacts.filter((a) => a.kind === "video").map((a) => (
                      <button key={a.id} type="button" role="radio" aria-checked={a.id === selectedVideo} className={`env-card ${a.id === selectedVideo ? "selected" : ""}`} onClick={() => setSelectedVideo(a.id)}>{a.name}</button>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {job.status === "failed" && (
        <div className="alert alert-error">
          <strong>Failed{job.failure_phase ? ` during ${job.failure_phase}` : ""}.</strong>{" "}
          {job.error ?? "The service did not provide a safe failure reason."}
        </div>
      )}
    </>
  );
}

function displayMetric(value: unknown): string {
  if (value === null) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}
