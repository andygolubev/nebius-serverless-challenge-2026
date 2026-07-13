export type MetricEntry = { label: string; value: string; rawKey: string };
export type EpisodeView = {
  index: string;
  reward: string;
  length: string;
  outcome: string;
  velocity: string;
};
export type ResultKpi = { label: string; value: string; emphasis?: boolean; title?: string };

export type ResultView = {
  kpis: ResultKpi[];
  evaluation: MetricEntry[];
  compute: MetricEntry[];
  run: MetricEntry[];
  episodes: EpisodeView[];
};

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function at(value: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((current, part) => {
    if (Array.isArray(current)) {
      const index = Number(part);
      return Number.isInteger(index) ? current[index] : undefined;
    }
    return record(current)[part];
  }, value);
}

function first(value: unknown, paths: string[]): unknown {
  for (const path of paths) {
    const candidate = at(value, path);
    if (candidate !== undefined && candidate !== null && candidate !== "") return candidate;
  }
  return undefined;
}

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\./g, " · ")
    .replace(/\b\w/g, (character: string) => character.toUpperCase())
    .replace("Gpu", "GPU")
    .replace("Id", "ID");
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${formatNumber(seconds)}s`;
  const whole = Math.round(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const remainder = whole % 60;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m ${remainder}s`;
}

function formatPercent(value: number): string {
  const normalized = Math.abs(value) <= 1 ? value * 100 : value;
  return `${formatNumber(normalized)}%`;
}

function formatCurrency(value: number, currency: string): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${formatNumber(value)} ${currency}`;
  }
}

export function formatMetric(key: string, value: unknown, currency = "USD"): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    const normalized = key.toLowerCase();
    if (normalized.includes("second") || normalized.endsWith("runtime")) return formatDuration(value);
    if (normalized.includes("percent") || normalized.includes("success_rate")) return formatPercent(value);
    if (normalized.includes("cost")) return formatCurrency(value, currency);
    return formatNumber(value);
  }
  if (Array.isArray(value)) {
    if (value.every((item) => ["string", "number", "boolean"].includes(typeof item))) {
      return value.map(String).join(", ");
    }
    return `${value.length} items`;
  }
  if (typeof value === "object") return "Structured data";
  return String(value);
}

function flatten(value: unknown, prefix = "", depth = 0): MetricEntry[] {
  if (depth > 3) return [];
  const entries: MetricEntry[] = [];
  for (const [key, item] of Object.entries(record(value))) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (item !== null && typeof item === "object" && !Array.isArray(item)) {
      entries.push(...flatten(item, path, depth + 1));
    } else {
      entries.push({ rawKey: path, label: humanize(path), value: formatMetric(path, item) });
    }
  }
  return entries;
}

function explicitEntry(metrics: unknown, label: string, paths: string[], currency = "USD"): MetricEntry | null {
  const value = first(metrics, paths);
  if (value === undefined) return null;
  return { rawKey: paths[0], label, value: formatMetric(paths[0], value, currency) };
}

export function buildResultView(metrics: Record<string, unknown>, fallbackEnvironment: string): ResultView {
  const currency = String(first(metrics, ["benchmark.currency", "currency"]) ?? "USD");
  const episodesRaw = first(metrics, ["episodes", "evaluation.episodes"]);
  const episodeRecords = Array.isArray(episodesRaw) ? episodesRaw.map(record) : [];
  const explicitSuccess = number(first(metrics, ["aggregate.success_rate", "evaluation.success_rate", "success_rate"]));
  const derivedSuccess = episodeRecords.length
    ? episodeRecords.filter((episode) => episode.fell === false || episode.success === true).length / episodeRecords.length
    : undefined;

  const reward = number(first(metrics, ["aggregate.mean_reward", "evaluation.mean_reward", "mean_reward", "reward"]));
  const runtime = number(first(metrics, ["runtime_seconds", "runtime.seconds", "evaluation_runtime_seconds"]));
  const cost = number(first(metrics, ["benchmark.estimated_cost", "estimated_cost", "cost"]));
  const utilization = number(first(metrics, [
    "benchmark.gpu_utilization_percent",
    "device.gpu.gpus.0.utilization_percent",
    "gpu_utilization_percent",
  ]));
  const environment = String(first(metrics, ["environment", "run.environment"]) ?? fallbackEnvironment);
  const checkpoint = String(first(metrics, ["checkpoint", "final_checkpoint", "run.checkpoint"]) ?? "—");

  const evaluation = [
    ...flatten(first(metrics, ["aggregate", "evaluation.aggregate"]) ?? {}),
    explicitEntry(metrics, "Evaluation runtime", ["evaluation_runtime_seconds"]),
  ].filter((entry): entry is MetricEntry => entry !== null);

  const compute = [
    explicitEntry(metrics, "Backend", ["backend"]),
    explicitEntry(metrics, "GPU available", ["device.gpu.available"]),
    explicitEntry(metrics, "GPU name", ["device.gpu.gpus.0.name"]),
    explicitEntry(metrics, "GPU utilization", ["device.gpu.gpus.0.utilization_percent"]),
    explicitEntry(metrics, "Requested device", ["device.requested"]),
    explicitEntry(metrics, "Platform", ["device.platform"]),
    ...flatten(first(metrics, ["benchmark"]) ?? {}, "benchmark"),
    ...flatten(first(metrics, ["device"]) ?? {}, "device"),
  ].filter((entry): entry is MetricEntry => entry !== null);

  const runCandidates = [
    explicitEntry(metrics, "Environment", ["environment"]),
    explicitEntry(metrics, "Final checkpoint", ["checkpoint", "final_checkpoint"]),
    explicitEntry(metrics, "Run ID", ["run_id"]),
    explicitEntry(metrics, "Runtime", ["runtime_seconds"]),
  ].filter((entry): entry is MetricEntry => entry !== null);

  const episodes = episodeRecords.map((episode, index) => ({
    index: String(episode.index ?? index),
    reward: formatMetric("reward", episode.reward),
    length: formatMetric("length", episode.length),
    outcome: episode.fell === true ? "Fell" : episode.success === false ? "Incomplete" : "Completed",
    velocity: formatMetric("mean_velocity", episode.mean_velocity),
  }));

  return {
    kpis: [
      { label: "Mean reward", value: reward === undefined ? "—" : formatNumber(reward), emphasis: true },
      { label: "Success", value: explicitSuccess === undefined && derivedSuccess === undefined ? "—" : formatPercent(explicitSuccess ?? derivedSuccess!) },
      { label: "Runtime", value: runtime === undefined ? "—" : formatDuration(runtime) },
      { label: "Estimated cost", value: cost === undefined ? "—" : formatCurrency(cost, currency) },
      { label: "GPU utilization", value: utilization === undefined ? "—" : formatPercent(utilization) },
      { label: "Environment", value: environment, title: environment },
      { label: "Final checkpoint", value: checkpoint, title: checkpoint },
    ],
    evaluation,
    compute,
    run: runCandidates,
    episodes,
  };
}
