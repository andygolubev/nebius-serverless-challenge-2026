import { LIFECYCLE, TERMINAL } from "../api";

export function StatusBadge({ status }: { status: string }) {
  const cls = status === "completed" ? "completed" : status === "failed" ? "failed" : "running";
  return (
    <span className={`badge ${cls}`}>
      {!TERMINAL.has(status) && <span className="pulse" aria-hidden />}
      {status}
    </span>
  );
}

// queued → starting → training → rendering → evaluating → completed
export function LifecycleTimeline({ status }: { status: string }) {
  const failed = status === "failed";
  const idx = failed ? LIFECYCLE.length - 1 : LIFECYCLE.indexOf(status);
  return (
    <div className="timeline" role="img" aria-label={`Job status: ${status}`}>
      {LIFECYCLE.map((step, i) => {
        const state = failed && i === idx ? "failed" : i < idx ? "done" : i === idx ? "current" : "";
        return (
          <span key={step} className={`timeline-step ${state}`}>
            {i > 0 && <span className={`timeline-bar ${i <= idx ? "done" : ""}`} aria-hidden />}
            <span className="timeline-dot" aria-hidden />
            <span className="timeline-label">{failed && i === idx ? "failed" : step}</span>
          </span>
        );
      })}
    </div>
  );
}

export function relativeTime(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function Skeletons({ count = 3 }: { count?: number }) {
  return (
    <div className="job-list" aria-hidden>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="skeleton" />
      ))}
    </div>
  );
}
