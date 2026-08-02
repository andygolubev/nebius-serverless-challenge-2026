// Result rendering shared by an owner's Job detail and the public showcase detail, so
// a curated showcase run and a tenant's own run read as the same product rather than
// two views that drifted apart.

import { useEffect, useRef, useState } from "react";
import { Artifact } from "../api";
import { buildResultView, MetricEntry } from "./resultView";

export const SIMULATOR_ONLY_NOTICE =
  "This policy bundle is simulator-only and is not directly deployable to a physical robot. Continue?";

export function formatBytes(value: number | null): string {
  if (value === null) return "Size unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MiB`;
}

export function KeyValue({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd title={value}>{value}</dd></div>;
}

export function SimulatorDisclosure() {
  return (
    <div className="alert alert-info simulator-disclosure" role="note">
      <strong>Simulator-only policy.</strong>
      <span>This bundle matches the recorded simulator and runtime. It is not directly deployable to physical hardware.</span>
    </div>
  );
}

export function BundleCallout({ bundle }: { bundle: Artifact }) {
  return (
    <div className="bundle-callout">
      <div>
        <strong>Policy bundle ready</strong>
        <span>Checkpoint, resolved configuration, evaluation, versions, and checksums. {formatBytes(bundle.size_bytes)}.</span>
      </div>
      <a
        className="btn btn-invert"
        href={bundle.download_url}
        onClick={(event) => {
          if (!window.confirm(SIMULATOR_ONLY_NOTICE)) event.preventDefault();
        }}
      >
        Download policy bundle
      </a>
    </div>
  );
}

/** Primary rollout player with label-selectable media and a retry on failure. */
export function MediaPanel({
  videos,
  selectedVideo,
  onSelectVideo,
}: {
  videos: Artifact[];
  selectedVideo: string | null;
  onSelectVideo: (id: string) => void;
}) {
  const [mediaError, setMediaError] = useState(false);
  const [mediaRetry, setMediaRetry] = useState(0);
  const [mediaPlaying, setMediaPlaying] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  useEffect(() => setMediaPlaying(false), [selectedVideo, mediaRetry]);

  const selected = videos.find((artifact) => artifact.id === selectedVideo) ?? videos[0];

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
    <div className="media-panel">
      <div className="result-section-heading">
        <div><p className="eyebrow">Policy rollout</p><h2>{selected?.name ?? "Final media"}</h2></div>
        {selected && <span className="metadata-line">{formatBytes(selected.size_bytes)}</span>}
      </div>
      {selected ? (
        <>
          {/* preload="metadata" keeps seeking available without fetching the whole file. */}
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
              <button
                className="btn btn-ghost"
                onClick={() => { setMediaError(false); setMediaRetry((value) => value + 1); }}
              >
                Retry playback
              </button>
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
  );
}

export function MetricDetails({
  title,
  subtitle,
  entries,
  defaultOpen = false,
}: {
  title: string;
  subtitle: string;
  entries: MetricEntry[];
  defaultOpen?: boolean;
}) {
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

export function EpisodeDetails({ episodes }: { episodes: ReturnType<typeof buildResultView>["episodes"] }) {
  return (
    <details className="result-detail">
      <summary>
        <strong>Episodes</strong>
        <span>{episodes.length ? `${episodes.length} evaluated` : "No episode list"}</span>
      </summary>
      {episodes.length ? (
        <div className="episode-table">
          <div className="episode-header" aria-hidden>
            <span>Episode</span><span>Reward</span><span>Length</span><span>Outcome</span><span>Mean velocity</span>
          </div>
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

export function ArtifactFiles({ artifacts, simulatorOnly }: { artifacts: Artifact[]; simulatorOnly: boolean }) {
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
                  if (simulatorOnly && artifact.id === "policy_bundle" && !window.confirm(SIMULATOR_ONLY_NOTICE)) {
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

/** Picks the final rollout as primary, falling back to the first available video. */
export function preferredVideoId(videos: Artifact[], current: string | null): string | null {
  if (current && videos.some((artifact) => artifact.id === current)) return current;
  const final = videos.find((artifact) => artifact.id.toLowerCase().includes("final")) ?? videos[0];
  return final?.id ?? null;
}
