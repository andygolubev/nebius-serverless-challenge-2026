import { useEffect, useMemo, useState } from "react";
import { api, ApiError, ArtifactManifest, Job, TERMINAL } from "../api";
import { LifecycleTimeline, relativeTime, StatusBadge } from "./shared";
import { buildResultView } from "./resultView";
import {
  ArtifactFiles,
  BundleCallout,
  EpisodeDetails,
  KeyValue,
  MediaPanel,
  MetricDetails,
  preferredVideoId,
  SimulatorDisclosure,
} from "./ResultPanels";

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
            setSelectedVideo((current) => preferredVideoId(videos, current));
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
  const bundle = artifacts.artifacts.find((artifact) => artifact.id === "policy_bundle");
  const otherFiles = artifacts.artifacts.filter((artifact) => artifact.kind !== "video" && artifact.id !== "policy_bundle");
  const kpis =
    job.job_kind === "custom-robot"
      ? view.kpis.filter((kpi) => !["GPU utilization", "Estimated cost"].includes(kpi.label))
      : view.kpis;
  const threshold = artifacts.metrics.aggregate as
    | { task_threshold_achieved?: boolean }
    | undefined;

  return (
    <section className="results-shell" aria-labelledby="results-heading">
      {(job.job_kind === "custom-robot" || job.gallery_example_id) && <SimulatorDisclosure />}
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
          {bundle && <BundleCallout bundle={bundle} />}
        </div>

        <MediaPanel videos={videos} selectedVideo={selectedVideo} onSelectVideo={onSelectVideo} />
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
