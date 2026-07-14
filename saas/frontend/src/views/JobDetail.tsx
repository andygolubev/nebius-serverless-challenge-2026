import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, Artifact, ArtifactManifest, Job, TERMINAL } from "../api";
import { LifecycleTimeline, relativeTime, StatusBadge } from "./shared";
import { buildResultView, MetricEntry } from "./resultView";

export function JobDetail({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactManifest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let alive = true;
    async function refresh() {
      try {
        const loadedJob = await api.getJob(jobId);
        if (!alive) return;
        setJob(loadedJob);
        setError(null);
        if (loadedJob.status === "completed") {
          try {
            const manifest = await api.getArtifacts(jobId);
            if (!alive) return;
            setArtifacts(manifest);
            setArtifactError(false);
            const videos = manifest.artifacts.filter((artifact) => artifact.kind === "video");
            const final = videos.find((artifact) => artifact.id.toLowerCase().includes("final")) ?? videos[0];
            setSelectedVideo((current) =>
              current && videos.some((artifact) => artifact.id === current) ? current : final?.id ?? null,
            );
          } catch (cause) {
            if (alive && (!(cause instanceof ApiError) || cause.status !== 409)) setArtifactError(true);
          }
        }
      } catch {
        if (alive) setError("Couldn't load this job. It may have been removed.");
      }
    }
    refresh();
    const timer = setInterval(() => {
      if (job && TERMINAL.has(job.status) && (job.status !== "completed" || artifacts)) return;
      refresh();
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [jobId, job?.status, artifacts !== null, retry]);

  if (error) {
    return (
      <>
        <button className="btn-link" onClick={onBack}>← Back to jobs</button>
        <div className="alert alert-error">{error}</div>
      </>
    );
  }
  if (!job) return <div className="skeleton" style={{ height: "12rem" }} aria-label="Loading job" />;

  return (
    <div className="job-detail">
      <button className="btn-link back-link" onClick={onBack}>← Back to jobs</button>
      <header className="job-detail-header">
        <div className="job-title-row">
          <div className="job-title-identity">
            {job.resolved_config.example?.avatar && <img src={job.resolved_config.example.avatar} alt="" />}
            <div>
              <p className="eyebrow">{job.job_kind === "custom-robot" ? "Uploaded robot training" : job.gallery_example_id ? "Verified example" : "Training job"}</p>
              <h1>
                {job.job_kind === "custom-robot"
                  ? `${job.resolved_config.robot?.name ?? "Uploaded robot"} · ${job.resolved_config.setup?.task_template_id?.replace(/-/g, " ") ?? "Custom locomotion"}`
                  : job.resolved_config.example
                    ? `${job.resolved_config.example.label} · ${job.resolved_config.example.task}`
                    : `${job.environment} · ${job.algorithm}`}
              </h1>
            </div>
          </div>
          <StatusBadge status={job.status} />
        </div>
        <p className="job-meta" title={job.id}>
          <span>#{job.id}</span>
          <span>Created {relativeTime(job.created_at)}</span>
          <span>Updated {relativeTime(job.updated_at)}</span>
        </p>
        <LifecycleTimeline status={job.status} />
      </header>

      {job.status === "finalizing" && (
        <div className="alert alert-info finalizing-callout" role="status">
          <strong>Training is complete.</strong> Reports and playable media are being finalized.
        </div>
      )}

      {job.status === "completed" && (
        <CompletedResults
          job={job}
          artifacts={artifacts}
          artifactError={artifactError}
          selectedVideo={selectedVideo}
          onSelectVideo={setSelectedVideo}
          onRetry={() => { setArtifactError(false); setRetry((value) => value + 1); }}
        />
      )}

      {job.status === "failed" && (
        <div className="failure-panel" role="alert">
          <span className="failure-icon" aria-hidden>!</span>
          <div>
            <h2>Failed{job.failure_phase ? ` during ${job.failure_phase}` : ""}</h2>
            <p>{job.error ?? "The service did not provide a safe failure reason."}</p>
          </div>
        </div>
      )}

      <details className="configuration-details" open={job.status !== "completed"}>
        <summary>
          Configuration
          <span>{job.job_kind === "custom-robot" ? "custom-ppo-quick · CPU" : job.preset ?? "Custom catalog settings"}</span>
        </summary>
        <dl className="compact-kv">
          {job.job_kind === "custom-robot" ? (
            <>
              <KeyValue label="Robot" value={job.resolved_config.robot?.name ?? job.environment} />
              <KeyValue label="Robot type" value={job.resolved_config.robot?.robot_type ?? "—"} />
              <KeyValue label="Task" value={job.resolved_config.setup?.task_template_id?.replace(/-/g, " ") ?? "—"} />
              <KeyValue label="Scene" value={job.resolved_config.setup?.scene_preset_id?.replace(/-/g, " ") ?? "—"} />
              <KeyValue label="Profile" value="custom-ppo-quick" />
              <KeyValue label="Compute" value={`${job.resolved_config.training?.platform ?? "cpu-d3"} · ${job.resolved_config.training?.preset ?? "8vcpu-32gb"}`} />
              <KeyValue label="Preparation fingerprint" value={job.preparation_fingerprint ?? "—"} />
            </>
          ) : (
            <>
              {job.resolved_config.example && <KeyValue label="Example" value={job.resolved_config.example.label} />}
              {job.preset && <KeyValue label="Preset" value={job.preset} />}
              <KeyValue label="Environment" value={job.resolved_config.environment ?? job.environment} />
              <KeyValue label="Algorithm" value={job.resolved_config.algorithm ?? job.algorithm} />
              {Object.entries(job.resolved_config.params ?? {}).map(([key, value]) => (
                <KeyValue key={key} label={key.replace(/_/g, " ")} value={String(value)} />
              ))}
            </>
          )}
        </dl>
      </details>
    </div>
  );
}

function CompletedResults({
  job,
  artifacts,
  artifactError,
  selectedVideo,
  onSelectVideo,
  onRetry,
}: {
  job: Job;
  artifacts: ArtifactManifest | null;
  artifactError: boolean;
  selectedVideo: string | null;
  onSelectVideo: (id: string) => void;
  onRetry: () => void;
}) {
  const view = useMemo(
    () => buildResultView(artifacts?.metrics ?? {}, job.environment),
    [artifacts, job.environment],
  );
  const [mediaError, setMediaError] = useState(false);
  const [mediaRetry, setMediaRetry] = useState(0);
  const [mediaPlaying, setMediaPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => setMediaPlaying(false), [selectedVideo, mediaRetry]);
  if (artifactError) {
    return (
      <div className="alert alert-error result-loading-error" role="alert">
        Results could not be loaded.
        <button className="btn btn-ghost" onClick={onRetry}>Retry results</button>
      </div>
    );
  }
  if (!artifacts) return <div className="skeleton result-skeleton" aria-label="Loading results" />;

  const videos = artifacts.artifacts.filter((artifact) => artifact.kind === "video");
  const selected = videos.find((artifact) => artifact.id === selectedVideo) ?? videos[0];
  const bundle = artifacts.artifacts.find((artifact) => artifact.id === "policy_bundle");
  const otherFiles = artifacts.artifacts.filter((artifact) => artifact.kind !== "video" && artifact.id !== "policy_bundle");
  const kpis =
    job.job_kind === "custom-robot"
      ? view.kpis.filter((kpi) => !["GPU utilization", "Estimated cost"].includes(kpi.label))
      : view.kpis;
  const threshold = artifacts.metrics.aggregate as
    | { task_threshold_achieved?: boolean }
    | undefined;

  async function togglePlayback() {
    const player = videoRef.current;
    if (!player) return;
    if (mediaPlaying) {
      player.pause();
      return;
    }
    try {
      await player.play();
    } catch {
      setMediaError(true);
    }
  }

  return (
    <section className="results-shell" aria-labelledby="results-heading">
      {(job.job_kind === "custom-robot" || job.gallery_example_id) && (
        <div className="alert alert-info simulator-disclosure" role="note">
          <strong>Simulator-only policy.</strong> This bundle matches the recorded simulator and runtime. It is not directly deployable to physical hardware.
        </div>
      )}
      <div className="result-primary-grid">
          <div className="result-summary-panel">
          <div className="result-section-heading">
            <div>
              <p className="eyebrow">Completed run</p>
              <h2 id="results-heading">Training result</h2>
            </div>
            <span className={`badge ${threshold?.task_threshold_achieved === false ? "warning" : "completed"}`}>
              {threshold?.task_threshold_achieved === false ? "Below task threshold" : "Artifacts ready"}
            </span>
          </div>
          <div className="kpi-grid">
            {kpis.map((kpi) => (
              <div className={`kpi ${kpi.emphasis ? "primary" : ""}`} key={kpi.label}>
                <span>{kpi.label}</span>
                <strong title={kpi.title}>{kpi.value}</strong>
              </div>
            ))}
          </div>
          {bundle && (
            <div className="bundle-callout">
              <div><strong>Policy bundle ready</strong><span>Checkpoint, resolved configuration, evaluation, versions, and checksums.</span></div>
              <a
                className="btn"
                href={bundle.download_url}
                onClick={(event) => {
                  if (!window.confirm("This policy bundle is simulator-only and is not directly deployable to a physical robot. Continue?")) {
                    event.preventDefault();
                  }
                }}
              >
                Download policy bundle
              </a>
            </div>
          )}
        </div>

        <div className="media-panel">
          <div className="result-section-heading">
            <div><p className="eyebrow">Policy rollout</p><h2>{selected?.name ?? "Final media"}</h2></div>
            {selected && <span className="metadata-line">{formatBytes(selected.size_bytes)}</span>}
          </div>
          {selected ? (
            <>
              <video
                key={`${selected.id}-${mediaRetry}`}
                ref={videoRef}
                controls
                preload="metadata"
                src={selected.url}
                onPlay={() => setMediaPlaying(true)}
                onPause={() => setMediaPlaying(false)}
                onEnded={() => setMediaPlaying(false)}
                onError={() => setMediaError(true)}
              >
                Your browser does not support HTML5 video.
              </video>
              {mediaError && (
                <div className="alert alert-error media-error" role="alert">
                  Playback failed to load.
                  <button className="btn btn-ghost" onClick={() => { setMediaError(false); setMediaRetry((value) => value + 1); }}>Retry playback</button>
                </div>
              )}
              <div className="media-actions">
                <button
                  className="btn btn-ghost"
                  type="button"
                  aria-label={mediaPlaying ? "Pause rollout" : "Play rollout"}
                  onClick={togglePlayback}
                >
                  {mediaPlaying ? "Pause" : "Play"}
                </button>
                <a className="btn btn-ghost" href={selected.url} target="_blank" rel="noreferrer">Open media</a>
                <a className="btn btn-ghost" href={selected.download_url}>Download</a>
              </div>
              {videos.length > 1 && (
                <div className="media-selector" role="radiogroup" aria-label="Select rollout media">
                  {videos.map((video) => (
                    <button
                      key={video.id}
                      type="button"
                      role="radio"
                      aria-checked={video.id === selected.id}
                      className={video.id === selected.id ? "selected" : ""}
                      onClick={() => { setMediaError(false); onSelectVideo(video.id); }}
                      title={video.name}
                    >
                      <span aria-hidden>▶</span>{video.name}
                    </button>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="no-media">This completed run has metrics but no playable rollout media.</div>
          )}
        </div>
      </div>

      <div className="semantic-details">
        <MetricDetails title="Evaluation" subtitle={`${view.evaluation.length} measurements`} entries={view.evaluation} defaultOpen />
        <EpisodeDetails episodes={view.episodes} />
        <MetricDetails title="Compute" subtitle={`${view.compute.length} properties`} entries={view.compute} />
        <MetricDetails title="Run" subtitle={`${view.run.length} identifiers`} entries={view.run} />
      </div>

      {otherFiles.length > 0 && (
        <ArtifactFiles artifacts={otherFiles} simulatorOnly={job.job_kind === "custom-robot" || !!job.gallery_example_id} />
      )}

      <details className="raw-diagnostics">
        <summary>Raw diagnostics <span>Structured JSON for debugging</span></summary>
        <pre>{JSON.stringify(artifacts.metrics, null, 2)}</pre>
      </details>
    </section>
  );
}

function MetricDetails({ title, subtitle, entries, defaultOpen = false }: { title: string; subtitle: string; entries: MetricEntry[]; defaultOpen?: boolean }) {
  return (
    <details className="result-detail" open={defaultOpen}>
      <summary><strong>{title}</strong><span>{subtitle}</span></summary>
      {entries.length ? (
        <dl className="metric-list">
          {entries.map((entry) => <KeyValue key={entry.rawKey} label={entry.label} value={entry.value} />)}
        </dl>
      ) : <p className="detail-empty">No {title.toLowerCase()} metrics were published.</p>}
    </details>
  );
}

function EpisodeDetails({ episodes }: { episodes: ReturnType<typeof buildResultView>["episodes"] }) {
  return (
    <details className="result-detail">
      <summary><strong>Episodes</strong><span>{episodes.length ? `${episodes.length} evaluated` : "No episode list"}</span></summary>
      {episodes.length ? (
        <div className="episode-table">
          <div className="episode-header" aria-hidden><span>Episode</span><span>Reward</span><span>Length</span><span>Outcome</span><span>Mean velocity</span></div>
          {episodes.map((episode, index) => (
            <div className="episode-row" key={`${episode.index}-${index}`}>
              <EpisodeCell label="Episode" value={episode.index} />
              <EpisodeCell label="Reward" value={episode.reward} />
              <EpisodeCell label="Length" value={episode.length} />
              <EpisodeCell label="Outcome" value={episode.outcome} />
              <EpisodeCell label="Mean velocity" value={episode.velocity} />
            </div>
          ))}
        </div>
      ) : <p className="detail-empty">This run did not publish per-episode rows.</p>}
    </details>
  );
}

function EpisodeCell({ label, value }: { label: string; value: string }) {
  return <span><small>{label}</small><strong>{value}</strong></span>;
}

function ArtifactFiles({ artifacts, simulatorOnly }: { artifacts: Artifact[]; simulatorOnly: boolean }) {
  return (
    <details className="result-detail artifact-files">
      <summary><strong>Result files</strong><span>{artifacts.length} downloadable</span></summary>
      <ul>
        {artifacts.map((artifact) => (
          <li key={artifact.id}>
            <span><strong>{artifact.name}</strong><small>{formatBytes(artifact.size_bytes)}</small></span>
            <span>
              <a href={artifact.url} target="_blank" rel="noreferrer">Open</a>
              <a
                href={artifact.download_url}
                onClick={(event) => {
                  if (
                    simulatorOnly &&
                    artifact.id === "policy_bundle" &&
                    !window.confirm("This policy bundle is simulator-only and is not directly deployable to a physical robot. Continue?")
                  ) {
                    event.preventDefault();
                  }
                }}
              >
                Download
              </a>
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd title={value}>{value}</dd></div>;
}

function formatBytes(value: number | null): string {
  if (value === null) return "Size unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}
