// Reference implementation for saas/frontend/src/views/Showcase.tsx (list view only).
// Design reference: "Verified Runs v2 light.dc.html". Adapt to the codebase's conventions;
// ShowcaseDetail is unchanged and omitted here, as are the exported format* helpers
// (formatDuration / formatCost / formatMetric / formatTimesteps) — keep them, the detail
// view and the unit tests still import them.

import { useEffect, useState } from "react";
import { api, ShowcaseEntry } from "../api";

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
          <h1>
            Watch robots
            <br />
            learn to move
          </h1>
          <p className="showcase-lede">
            Seven policies trained on real hardware and recorded end to end — policy weights,
            metrics and rollout video. Browse them freely, then bring your own robot.
          </p>
          <div className="hero-actions">
            <a className="btn" href="#gallery">Browse the seven runs</a>
            {!authed && (
              <button className="btn btn-ghost" onClick={onSignIn}>
                Sign in to train your own
              </button>
            )}
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
              <div>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="showcase-wrap">
        <div className="gallery-head">
          <h2 id="gallery">The gallery</h2>
          <p>
            {entries ? `${entries.length} runs` : "Loading"}
            {revision ? ` · revision ${revision}` : ""}
          </p>
        </div>

        {failed && (
          <div className="alert alert-error" role="alert">
            The showcase could not be loaded right now. Please try again shortly.
          </div>
        )}

        <div className="gallery-grid" aria-busy={entries === null && !failed}>
          {entries === null && !failed &&
            [0, 1, 2].map((index) => (
              <div className="gallery-card" key={index}>
                <div className="skeleton" style={{ height: "18rem" }} />
              </div>
            ))}

          {entries?.map((entry, index) => (
            <ShowcaseCard
              key={entry.id}
              entry={entry}
              index={index}
              onOpen={() => onOpenExample(entry.id)}
            />
          ))}

          {/* The only training path offered anywhere on the showcase. */}
          <div className="gallery-poster">
            <p className="kicker">Your turn</p>
            <p className="statement">Bring your own robot.</p>
            <p>
              Free of charge — no credit card. Give an email, get a personal space, upload a model,
              build a bounded environment and train it.
            </p>
            <button className="btn btn-invert" onClick={onSignIn}>
              {authed ? "Go to My Robots →" : "Sign in to train →"}
            </button>
          </div>
        </div>

        {entries !== null && entries.length === 0 && (
          <div className="empty-state" role="status">
            <h2>Verified runs are being prepared</h2>
            <p>
              The training runs for this showcase are still being produced. Each one appears here as
              soon as its policy, metrics, and rollout video are recorded and validated.
            </p>
          </div>
        )}
      </div>

      <section className="showcase-band">
        <div className="showcase-band-inner">
          <p className="band-label">What every run leaves behind</p>
          <div className="band-cols">
            {KEEPS.map((keep) => (
              <div key={keep.title}>
                <h3>{keep.title}</h3>
                <p>{keep.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="credit">
        <div className="credit-inner">
          <p className="credit-label">Built with passion and love</p>
          <p className="credit-statement">
            Simulation, training, storage, deployment and this page — built in weeks by one person
            with an LLM. That is the time we live in, and I loved every hour of it.
          </p>
        </div>
      </section>

      <footer className="site-footer">
        <div className="site-footer-inner">
          <span className="wordmark">Sim2Policy</span>
          <nav aria-label="Footer">
            <a href="#about">About me</a>
            <a href="#terms">Terms of use</a>
          </nav>
          <span className="meta">Nebius Serverless Challenge 2026</span>
        </div>
      </footer>
    </div>
  );
}

function ShowcaseCard({
  entry,
  index,
  onOpen,
}: {
  entry: ShowcaseEntry;
  index: number;
  onOpen: () => void;
}) {
  return (
    // One button per card: the accessible name carries label and task, so the avatar
    // stays decorative and screen readers do not depend on it.
    <button
      className="gallery-card"
      type="button"
      onClick={onOpen}
      aria-label={`${entry.label} — ${entry.task}`}
    >
      <div className="gallery-card-top">
        <span className="gallery-index">{String(index + 1).padStart(2, "0")}</span>
        <EvaluationBadge entry={entry} />
      </div>
      <img src={entry.avatar} alt="" />
      <div>
        <p className="card-task">{entry.task}</p>
        <h3>{entry.label}</h3>
        <p className="card-desc">{entry.description}</p>
      </div>
      <dl className="gallery-card-facts">
        <div>
          <dt>Backend</dt>
          <dd>{entry.backend_label}</dd>
        </div>
        <div>
          <dt>Hardware</dt>
          <dd>{entry.hardware_label}</dd>
        </div>
        <div>
          <dt>Criterion</dt>
          <dd>{entry.evaluation.criterion}</dd>
        </div>
      </dl>
      <p className="recommended-line">
        {entry.has_media ? "Watch the rollout" : "Inspect the run"} →
      </p>
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
  {
    title: "Keep",
    body: "Policy, metrics and rollout video land in durable storage — the machine can go away.",
  },
];

const KEEPS = [
  {
    title: "A policy you can replay",
    body: "Checkpoint weights and the exact executed configuration — environment, algorithm, timesteps, seed.",
  },
  {
    title: "Measured, not claimed",
    body: "Observed runtime and cost recorded from the job itself, next to the success criterion it was judged against.",
  },
  {
    title: "A rollout video",
    body: "Rendered from the trained policy, so the result is watchable and not only a number on a chart.",
  },
];
