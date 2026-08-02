// The public, unauthenticated showcase: evidence from curated runs that already
// happened. Deliberately contains no control that starts, re-runs, forks, or queues a
// training job — the only call to action is to sign in and train your own robot.

import { useEffect, useMemo, useState } from "react";
import { api, ApiError, ShowcaseDetail as ShowcaseDetailData, ShowcaseEntry } from "../api";
import { Credit } from "./About";
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

// The API reports measured runtime and cost as numbers, which is right for a
// machine contract and unreadable on a public page: an unformatted value renders
// as "1038.543337257" and "0.8510285680300418". Formatting stays here so the
// payload keeps its precision.
export function formatDuration(value: number | string): string {
  const seconds = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(seconds)) return String(value);
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60) return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${minutes % 60} min`;
}

export function formatCost(value: number | string): string {
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  // Sub-cent runs are real here, so they round up to the smallest shown unit
  // rather than displaying as "$0.00".
  return amount > 0 && amount < 0.01 ? "<$0.01" : `$${amount.toFixed(2)}`;
}

// The curated primary metric is a measured float too, so it lands on the page as
// "0.9750489678259939" without help. Three decimals is enough to compare against a
// published threshold, and trailing zeros are dropped so "20" does not read "20.000".
export function formatMetric(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(amount)) return String(value);
  return String(Number(amount.toFixed(3)));
}

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

  const revision = entries?.[0]?.acceptance_revision;

  return (
    <div className="showcase">
      <section className="showcase-hero">
        <div>
          <p className="eyebrow">Verified training runs · Nebius Serverless Challenge 2026</p>
          <h1>Watch robots<br />learn to move</h1>
          <p className="showcase-lede">
            Seven policies trained on real hardware and recorded end to end — policy weights,
            metrics and rollout video. Browse them freely, then bring your own robot.
          </p>
          <div className="hero-actions">
            <a className="btn" href="#gallery">Browse the seven runs</a>
            <button className="btn btn-ghost" onClick={onSignIn}>
              {authed ? "Go to My Robots" : "Sign in to train your own"}
            </button>
          </div>
          <p className="hero-note">
            This is my project for the <strong>Nebius Serverless Challenge 2026</strong> — so it is
            free of charge for you. No credit card. Just your email, and you get a personal space
            where you can train your own robots.
          </p>
        </div>

        <div className="pipeline">
          <p className="pipeline-label">How a run happens</p>
          {PIPELINE.map((step, index) => (
            <div className="pipeline-step" key={step.title}>
              <b>{String(index + 1).padStart(2, "0")}</b>
              <div><h3>{step.title}</h3><p>{step.body}</p></div>
            </div>
          ))}
        </div>
      </section>

      <div className="showcase-wrap">
        <div className="gallery-head">
          <h2 id="gallery">The gallery</h2>
          <p>{entries ? `${entries.length} runs` : "Loading"}{revision ? ` · revision ${revision}` : ""}</p>
        </div>

        {failed && (
          <div className="alert alert-error" role="alert">
            The showcase could not be loaded right now. Please try again shortly.
          </div>
        )}

        <div className="gallery-grid" aria-busy={entries === null && !failed}>
          {entries === null && !failed && [0, 1, 2].map((index) => (
            <div className="gallery-card gallery-skeleton" key={index}>
              <div className="skeleton" style={{ height: "20rem" }} />
            </div>
          ))}
          {entries?.map((entry, index) => (
            <ShowcaseCard key={entry.id} entry={entry} index={index} onOpen={() => onOpenExample(entry.id)} />
          ))}
          {entries !== null && (
            <div className="gallery-poster">
              <p className="kicker">Your turn</p>
              <p className="statement">Bring your own robot.</p>
              <p>Free of charge — no credit card. Give an email, get a personal space, upload a model, build a bounded environment and train it.</p>
              <button className="btn btn-invert" onClick={onSignIn}>
                {authed ? "Go to My Robots →" : "Sign in to train →"}
              </button>
            </div>
          )}
        </div>

        {entries !== null && entries.length === 0 && (
          <div className="empty-state" role="status">
            <h2>Verified runs are being prepared</h2>
            <p>The training runs for this showcase are still being produced. Each one appears here as soon as its policy, metrics, and rollout video are recorded and validated.</p>
          </div>
        )}
      </div>

      <section className="showcase-band">
        <div className="showcase-band-inner">
          <p className="band-label">What every run leaves behind</p>
          <div className="band-cols">
            {KEEPS.map((keep) => <div key={keep.title}><h3>{keep.title}</h3><p>{keep.body}</p></div>)}
          </div>
        </div>
      </section>
      <Credit />
    </div>
  );
}

function ShowcaseCard({ entry, index, onOpen }: { entry: ShowcaseEntry; index: number; onOpen: () => void }) {
  return (
    // A single button per card: the accessible name carries the label and task, so
    // the avatar stays decorative and screen readers do not depend on it.
    <button className="gallery-card" type="button" onClick={onOpen} aria-label={`${entry.label} — ${entry.task}`}>
      <div className="gallery-card-top">
        <span className="gallery-index">{String(index + 1).padStart(2, "0")}</span>
        <EvaluationBadge entry={entry} />
      </div>
      <img src={entry.avatar} alt="" />
      <div><p className="card-task">{entry.task}</p><h3>{entry.label}</h3><p className="card-desc">{entry.description}</p></div>
      <dl className="gallery-card-facts">
        <KeyValue label="Backend" value={entry.backend_label} />
        <KeyValue label="Hardware" value={entry.hardware_label} />
        <KeyValue label="Criterion" value={entry.evaluation.criterion} />
      </dl>
      <p className="recommended-line">{entry.has_media ? "Watch the rollout" : "Inspect the run"} →</p>
    </button>
  );
}

function EvaluationBadge({ entry }: { entry: ShowcaseEntry }) {
  if (entry.evaluation.success === false) {
    return <span className="tag below" title={entry.evaluation.criterion}>Below task threshold</span>;
  }
  if (entry.evaluation.success === true) {
    return <span className="tag" title={entry.evaluation.criterion}>Met task threshold</span>;
  }
  return <span className="tag neutral" title={entry.evaluation.criterion}>Recorded run</span>;
}

const PIPELINE = [
  { title: "Simulate", body: "MuJoCo physics — no physical robot, no lab time." },
  { title: "Train", body: "PPO as a serverless AI job — SB3 on CPU, MJX/JAX on GPU." },
  { title: "Keep", body: "Policy, metrics and rollout video land in durable storage — the machine can go away." },
];

const KEEPS = [
  { title: "A policy you can replay", body: "Checkpoint weights and the exact executed configuration — environment, algorithm, timesteps, seed." },
  { title: "Measured, not claimed", body: "Observed runtime and cost recorded from the job itself, next to the success criterion it was judged against." },
  { title: "A rollout video", body: "Rendered from the trained policy, so the result is watchable and not only a number on a chart." },
];

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
              <KeyValue label="Primary metric" value={formatMetric(detail.evaluation.primary_metric)} />
              <KeyValue label="Observed duration" value={formatDuration(detail.observed_duration)} />
              <KeyValue label="Observed cost" value={formatCost(detail.observed_cost)} />
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
