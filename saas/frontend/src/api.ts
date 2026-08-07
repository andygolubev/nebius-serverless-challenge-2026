// Typed API client. Injects the bearer session token and broadcasts a logout
// event on any 401 so the app can drop back to the login screen.

// -- public showcase --
// Read-only evidence from curated runs that already happened. No submission shape:
// there is nothing here a visitor can start.

export type ShowcaseEvaluation = {
  // Whether the run met its task threshold — separate from whether the run finished.
  success: boolean | null;
  criterion: string;
  primary_metric: string;
};

export type ShowcaseExecutedConfig = {
  environment: string;
  environment_label: string;
  algorithm_label: string;
  total_timesteps: number | null;
  platform: string | null;
  preset: string | null;
};

export type ShowcaseEntry = {
  id: string;
  label: string;
  task: string;
  description: string;
  avatar: string;
  expected_result: string;
  backend_label: string;
  hardware_label: string;
  observed_duration: string;
  observed_cost: string;
  acceptance_revision: string;
  executed_config: ShowcaseExecutedConfig;
  evaluation: ShowcaseEvaluation;
  has_media: boolean;
};

export type ShowcaseDetail = ShowcaseEntry & {
  // Infrastructure completion, reported separately from `evaluation`.
  status: string;
  metrics: Record<string, unknown>;
  artifacts: Artifact[];
};

export type ResolvedConfig = Record<string, unknown> & {
  environment?: string;
  algorithm?: string;
  params?: Record<string, number>;
  robot?: { id: string; name: string; robot_type: RobotType; digest: string };
  setup?: { id: string; name: string; task_template_id: string; scene_preset_id: string };
  training?: { version?: string; platform?: string; preset?: string; total_timesteps?: number };
  example?: { id: string; label: string; avatar: string; task: string };
  profile?: string;
  success?: { criterion?: string; primary_metric?: string };
};

export type Job = {
  id: string;
  preset: string | null;
  environment: string;
  algorithm: string;
  resolved_config: ResolvedConfig;
  status: string;
  created_at: string;
  updated_at: string;
  nebius_job_id?: string | null;
  error?: string | null;
  phase?: string | null;
  failure_phase?: string | null;
  artifacts_status: string;
  job_kind: "catalog" | "custom-robot";
  robot_id?: string | null;
  setup_id?: string | null;
  preparation_id?: string | null;
  preparation_fingerprint?: string | null;
  gallery_example_id?: string | null;
};

export type Artifact = {
  id: string;
  name: string;
  kind: "video" | "image" | "file";
  content_type: string;
  size_bytes: number | null;
  url: string;
  download_url: string;
};

export type ArtifactManifest = {
  job_id: string;
  status: string;
  metrics: Record<string, unknown>;
  media: string[];
  artifacts: Artifact[];
};

export type FieldError = { field: string; message: string };

export type RobotType = "quadruped" | "biped";

export type RobotValidation = {
  body_count: number;
  joint_count: number;
  actuator_count: number;
  geom_count: number;
  joint_names: string[];
  actuator_names: string[];
};

export type Robot = {
  id: string;
  name: string;
  filename: string;
  robot_type: RobotType;
  digest: string;
  validation: RobotValidation;
  validated_at: string;
  readiness: "validated";
  trainable: false;
  reason: "custom-training-not-enabled";
};

export type RobotSample = {
  id: string;
  name: string;
  filename: string;
  description: string;
  robot_type: RobotType;
  digest: string;
  validation: RobotValidation;
};

export type CatalogObjectInput = {
  object_type: "box" | "ramp" | "hurdle" | "step";
  x?: number;
  y?: number;
  z?: number;
  yaw_degrees?: number;
  width?: number;
  depth?: number;
  height?: number;
};

export type CatalogObject = Required<CatalogObjectInput> & { source: "preset" | "custom" };

export type ObjectParameter = {
  name: keyof Omit<CatalogObjectInput, "object_type">;
  label: string;
  default: number;
  minimum: number;
  maximum: number;
  unit: string;
};

export type ObjectCatalogEntry = {
  id: CatalogObjectInput["object_type"];
  label: string;
  description: string;
  parameters: ObjectParameter[];
};

export type TaskTemplate = {
  id: "stand-balance" | "walk-forward" | "recover-from-fall";
  label: string;
  description: string;
  compatible_robot_types: RobotType[];
  contract: Record<string, string>;
};

export type ScenePreset = {
  id: "flat-arena" | "ramp-course" | "hurdle-course" | "step-course";
  label: string;
  description: string;
  objects: CatalogObject[];
};

export type EnvironmentCatalog = {
  task_templates: TaskTemplate[];
  scene_presets: ScenePreset[];
  object_types: ObjectCatalogEntry[];
  max_objects: number;
  max_setups: number;
  arena_bounds: Record<string, [number, number]>;
};

export type RobotSetupRequest = {
  name: string;
  robot_id: string;
  task_template_id: string;
  scene_preset_id: string;
  objects: CatalogObjectInput[];
};

export type RobotSetup = {
  id: string;
  name: string;
  robot_id: string;
  robot_name: string;
  robot_type: RobotType;
  task_template_id: string;
  scene_preset_id: string;
  objects: CatalogObject[];
  digest: string;
  created_at: string;
  readiness: "validated";
  trainable: boolean;
  reason: string;
  training_readiness: TrainingReadiness;
  can_prepare: boolean;
  can_start_training: boolean;
  current_preparation: Preparation | null;
  latest_training_job?: TrainingJobSummary | null;
};

export type TrainingJobSummary = {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  artifacts_status: string;
};

export type TrainingReadiness =
  | "ineligible"
  | "not_prepared"
  | "preparing"
  | "ready"
  | "preparation_failed";

export type Preparation = {
  id: string;
  setup_id: string;
  robot_id: string;
  fingerprint: string;
  state: "queued" | "preparing" | "accepted" | "failed";
  phase: string;
  created_at: string;
  updated_at: string;
  failure_phase: string | null;
  failure_reason: string | null;
  report_sha256: string | null;
  report_ready: boolean;
  can_retry: boolean;
};

export class ApiError extends Error {
  status: number;
  fieldError: FieldError | null;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(
      typeof detail === "string"
        ? detail
        : detail && typeof detail === "object" && "message" in detail
          ? String((detail as { message: unknown }).message)
          : "request failed",
    );
    this.status = status;
    this.detail = detail;
    this.fieldError =
      detail && typeof detail === "object" && "field" in (detail as object)
        ? (detail as FieldError)
        : null;
  }
}

const TOKEN_KEY = "sim2policy.session";
const EMAIL_KEY = "sim2policy.email";

export const session = {
  get token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  get email(): string | null {
    return localStorage.getItem(EMAIL_KEY);
  },
  set(token: string, email: string) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(EMAIL_KEY, email);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
  },
};

// Fired when a 401 invalidates the session; App listens and shows Login.
export const SESSION_EXPIRED_EVENT = "session-expired";

async function authorizedFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = session.token;
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(path, { ...init, headers });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    session.clear();
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await authorizedFetch(path, init);
  if (res.status === 204) return undefined as T;
  return res.json();
}

// Public reads send no Authorization header and never broadcast SESSION_EXPIRED_EVENT:
// a 404 on the showcase is not a session problem, and a signed-in visitor must get the
// same response as an anonymous one.
async function publicRequest<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {
      // non-JSON error body; keep statusText
    }
    throw new ApiError(res.status, detail);
  }
  return res.json();
}

// Fire-and-forget public writes intentionally bypass session handling. Analytics is
// not authenticated and a network failure must never sign a visitor out.
export function publicPost(path: string, body: unknown, init: RequestInit = {}): Promise<Response> {
  return fetch(path, {
    ...init,
    method: "POST",
    headers: { "Content-Type": "application/json", ...init.headers },
    body: JSON.stringify(body),
  });
}

async function requestBlob(path: string): Promise<Blob> {
  return (await authorizedFetch(path)).blob();
}

export const api = {
  requestCode: (email: string) =>
    request<{ status: string }>("/auth/request-code", { method: "POST", body: JSON.stringify({ email }) }),
  verifyCode: (email: string, code: string) =>
    request<{ token: string; email: string }>("/auth/verify", {
      method: "POST",
      body: JSON.stringify({ email, code }),
    }),
  logout: () => request<{ status: string }>("/auth/logout", { method: "POST" }),
  // Public, session-free showcase reads.
  showcase: () => publicRequest<{ examples: ShowcaseEntry[] }>("/showcase"),
  showcaseExample: (id: string) => publicRequest<ShowcaseDetail>(`/showcase/${encodeURIComponent(id)}`),
  listJobs: () => request<Job[]>("/jobs"),
  getJob: (id: string) => request<Job>(`/jobs/${id}`),
  getArtifacts: (id: string) => request<ArtifactManifest>(`/jobs/${id}/artifacts`),
  listRobotSamples: () => request<RobotSample[]>("/robot-samples"),
  downloadRobotSample: (id: string) => requestBlob(`/robot-samples/${encodeURIComponent(id)}`),
  listRobots: () => request<Robot[]>("/robots"),
  uploadRobot: (name: string, robotType: RobotType, file: File) => {
    const body = new FormData();
    body.set("name", name);
    body.set("robot_type", robotType);
    body.set("file", file);
    return request<Robot>("/robots", { method: "POST", body });
  },
  getRobot: (id: string) => request<Robot>(`/robots/${encodeURIComponent(id)}`),
  downloadRobot: (id: string) => requestBlob(`/robots/${encodeURIComponent(id)}/content`),
  deleteRobot: (id: string) => request<void>(`/robots/${encodeURIComponent(id)}`, { method: "DELETE" }),
  environmentCatalog: () => request<EnvironmentCatalog>("/environment-catalog"),
  listRobotSetups: () => request<RobotSetup[]>("/robot-setups"),
  createRobotSetup: (body: RobotSetupRequest) =>
    request<RobotSetup>("/robot-setups", { method: "POST", body: JSON.stringify(body) }),
  getRobotSetup: (id: string) => request<RobotSetup>(`/robot-setups/${encodeURIComponent(id)}`),
  deleteRobotSetup: (id: string) =>
    request<void>(`/robot-setups/${encodeURIComponent(id)}`, { method: "DELETE" }),
  prepareRobotSetup: (id: string, retry = false) =>
    request<Preparation>(`/robot-setups/${encodeURIComponent(id)}/preparations`, {
      method: "POST",
      body: JSON.stringify({ retry }),
    }),
  latestPreparation: (id: string) =>
    request<Preparation>(`/robot-setups/${encodeURIComponent(id)}/preparations/latest`),
  startRobotTraining: (id: string, idempotencyKey: string) =>
    request<Job>(`/robot-setups/${encodeURIComponent(id)}/training-jobs`, {
      method: "POST",
      body: JSON.stringify({ idempotency_key: idempotencyKey }),
    }),
};

export const LIFECYCLE = ["queued", "starting", "training", "finalizing", "rendering", "evaluating", "completed"];
export const TERMINAL = new Set(["completed", "failed"]);
