// The public, unauthenticated showcase: evidence from curated runs that already
// happened. Deliberately contains no control that starts, re-runs, forks, or queues a
// training job — the only call to action is to sign in and train your own robot.

import { useEffect, useMemo, useState } from "react";
import { api, ApiError, ShowcaseDetail as ShowcaseDetailData, ShowcaseEntry } from "../api";
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

export function Showcase({
  onOpenExample,
  onSignIn,
  authed,
}: {
  onOpenExample: (id: string) => void;
  onSignIn: () => void;
  authed: boolean;
}) {
  const [entries, setEntries] = useState<ShowcaseEntry[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .showcase()
      .then((result) => alive && setEntries(result.examples))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="showcase">
      <header className="showcase-hero">
        <p className="eyebrow">Verified training runs</p>
        <h1 className="section-title">Watch robots learn to move</h1>
        <p className="section-sub">
          Every run below was trained on real GPU hardware and recorded — policy, metrics, and rollout video. Browse
          them freely, then bring your own robot.
        </p>
        {!authed && (
          <button className="btn" onClick={onSignIn}>
            Sign in to train your own robot
          </button>
        )}
      </header>

      {failed && (
        <div className="alert alert-error" role="alert">
          The showcase could not be loaded right now. Please try again shortly.
        </div>
      )}

      {entries === null && !failed && (
        <div className="gallery-grid" aria-label="Loading verified runs">
          {[0, 1, 2].map((index) => (
            <div className="skeleton" style={{ height: "20rem" }} key={index} />
          ))}
        </div>
      )}

      {entries !== null && entries.length === 0 && (
        <div className="empty-state" role="status">
          <h2>Verified runs are being prepared</h2>
          <p>
            The training runs for this showcase are still being produced. Each one appears here as soon as its policy,
            metrics, and rollout video are recorded and validated.
          </p>
          {/* The hero already offers the sign-in call to action directly above. */}
        </div>
      )}

      {entries !== null && entries.length > 0 && (
        <div className="gallery-grid">
          {entries.map((entry) => (
            <ShowcaseCard key={entry.id} entry={entry} onOpen={() => onOpenExample(entry.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

function ShowcaseCard({ entry, onOpen }: { entry: ShowcaseEntry; onOpen: () => void }) {
  return (
    // A single button per card: the accessible name carries the label and task, so
    // the avatar stays decorative and screen readers do not depend on it.
    <button className="gallery-card" type="button" onClick={onOpen} aria-label={`${entry.label} — ${entry.task}`}>
      <div className="gallery-card-top">
        <img src={entry.avatar} alt="" />
        <EvaluationBadge entry={entry} />
      </div>
      <div className="gallery-card-copy">
        <p className="eyebrow">{entry.task}</p>
        <h2>{entry.label}</h2>
        <p>{entry.description}</p>
      </div>
      <div className="badge-row">
        <span className="badge backend-badge">{entry.backend_label}</span>
        <span className="badge">{entry.hardware_label}</span>
      </div>
      <dl className="gallery-card-facts">
        <KeyValue label="Observed duration" value={entry.observed_duration} />
        <KeyValue label="Observed cost" value={entry.observed_cost} />
        <KeyValue label="Timesteps" value={formatTimesteps(entry.executed_config.total_timesteps)} />
        <KeyValue label="Expected" value={entry.expected_result} />
      </dl>
      <p className="recommended-line">{entry.has_media ? "Watch the rollout" : "Inspect the run"} →</p>
    </button>
  );
}

function EvaluationBadge({ entry }: { entry: ShowcaseEntry }) {
  if (entry.evaluation.success === false) {
    return <span className="badge warning" title={entry.evaluation.criterion}>Below task threshold</span>;
  }
  if (entry.evaluation.success === true) {
    return <span className="badge completed" title={entry.evaluation.criterion}>Met task threshold</span>;
  }
  return <span className="badge" title={entry.evaluation.criterion}>Recorded run</span>;
}

export function ShowcaseDetail({
  exampleId,
  onBack,
  onSignIn,
  authed,
}: {
  exampleId: string;
  onBack: () => void;
  onSignIn: () => void;
  authed: boolean;
}) {
  const [detail, setDetail] = useState<ShowcaseDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setDetail(null);
    setError(null);
    api
      .showcaseExample(exampleId)
      .then((result) => {
        if (!alive) return;
        setDetail(result);
        const videos = result.artifacts.filter((artifact) => artifact.kind === "video");
        setSelectedVideo((current) => preferredVideoId(videos, current));
      })
      .catch((cause) => {
        if (!alive) return;
        setError(
          cause instanceof ApiError && cause.status === 404
            ? "This run is not available in the showcase."
            : "This run could not be loaded right now.",
        );
      });
    return () => {
      alive = false;
    };
  }, [exampleId]);

  const view = useMemo(() => buildResultView(detail?.metrics ?? {}, detail?.executed_config.environment ?? ""), [detail]);

  if (error) {
    return (
      <>
        <button className="btn-link back-link" onClick={onBack}>← Back to verified runs</button>
        <div className="alert alert-error" role="alert">{error}</div>
      </>
    );
  }
  if (!detail) return <div className="skeleton" style={{ height: "12rem" }} aria-label="Loading run" />;

  const videos = detail.artifacts.filter((artifact) => artifact.kind === "video");
  const bundle = detail.artifacts.find((artifact) => artifact.id === "policy_bundle");
  const otherFiles = detail.artifacts.filter(
    (artifact) => artifact.kind !== "video" && artifact.id !== "policy_bundle",
  );

  return (
    <div className="job-detail showcase-detail">
      <button className="btn-link back-link" onClick={onBack}>← Back to verified runs</button>
      <header className="job-detail-header">
        <div className="job-title-row">
          <div className="job-title-identity">
            <img src={detail.avatar} alt="" />
            <div>
              <p className="eyebrow">Verified example</p>
              <h1>{detail.label} · {detail.task}</h1>
            </div>
          </div>
          <EvaluationBadge entry={detail} />
        </div>
        <p className="job-meta">
          <span>{detail.backend_label}</span>
          <span>{detail.hardware_label}</span>
          <span>Revision {detail.acceptance_revision}</span>
        </p>
        <p className="showcase-description">{detail.description}</p>
      </header>

      <section className="results-shell" aria-labelledby="showcase-results-heading">
        {bundle && <SimulatorDisclosure />}
        <div className="result-primary-grid">
          <div className="result-summary-panel">
            <div className="result-section-heading">
              <div>
                <p className="eyebrow">Recorded run</p>
                <h2 id="showcase-results-heading">Training result</h2>
              </div>
              {/* Infrastructure completion, stated separately from the evaluation badge. */}
              <span className="badge completed">{detail.status === "completed" ? "Artifacts ready" : detail.status}</span>
            </div>
            <div className="kpi-grid">
              {view.kpis.map((kpi) => (
                <div className={`kpi ${kpi.emphasis ? "primary" : ""}`} key={kpi.label}>
                  <span>{kpi.label}</span>
                  <strong title={kpi.title}>{kpi.value}</strong>
                </div>
              ))}
            </div>
            <dl className="compact-kv">
              <KeyValue label="Success criterion" value={detail.evaluation.criterion} />
              <KeyValue label="Primary metric" value={detail.evaluation.primary_metric} />
              <KeyValue label="Observed duration" value={detail.observed_duration} />
              <KeyValue label="Observed cost" value={detail.observed_cost} />
            </dl>
            {bundle && <BundleCallout bundle={bundle} />}
          </div>

          <MediaPanel videos={videos} selectedVideo={selectedVideo} onSelectVideo={setSelectedVideo} />
        </div>

        <div className="semantic-details">
          <MetricDetails title="Evaluation" subtitle={`${view.evaluation.length} measurements`} entries={view.evaluation} defaultOpen />
          <EpisodeDetails episodes={view.episodes} />
          <MetricDetails title="Compute" subtitle={`${view.compute.length} properties`} entries={view.compute} />
          <MetricDetails title="Run" subtitle={`${view.run.length} identifiers`} entries={view.run} />
        </div>

        {otherFiles.length > 0 && <ArtifactFiles artifacts={otherFiles} simulatorOnly />}

        <details className="configuration-details">
          <summary>
            Configuration
            <span>{detail.executed_config.platform ?? "recorded run"}</span>
          </summary>
          <dl className="compact-kv">
            <KeyValue label="Environment" value={detail.executed_config.environment_label} />
            <KeyValue label="Algorithm" value={detail.executed_config.algorithm_label} />
            <KeyValue label="Timesteps" value={formatTimesteps(detail.executed_config.total_timesteps)} />
            <KeyValue label="Platform" value={detail.executed_config.platform ?? "—"} />
            <KeyValue label="Compute preset" value={detail.executed_config.preset ?? "—"} />
          </dl>
        </details>

        <details className="raw-diagnostics">
          <summary>Raw diagnostics <span>Structured JSON for debugging</span></summary>
          <pre>{JSON.stringify(detail.metrics, null, 2)}</pre>
        </details>
      </section>

      {/* The only training path offered anywhere on the showcase. */}
      <aside className="showcase-cta">
        <div>
          <strong>Want a policy for your own robot?</strong>
          <span>Upload a model, build a bounded environment, and train it on your own account.</span>
        </div>
        {authed ? (
          <button className="btn" onClick={onSignIn}>Go to My Robots</button>
        ) : (
          <button className="btn" onClick={onSignIn}>Sign in to train your own robot</button>
        )}
      </aside>
    </div>
  );
}

function formatTimesteps(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-US").format(value);
}
