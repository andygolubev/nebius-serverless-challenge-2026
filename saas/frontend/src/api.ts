// Typed API client. Injects the bearer session token and broadcasts a logout
// event on any 401 so the app can drop back to the login screen.

export type ParamSpec = {
  name: string;
  label: string;
  type: "int" | "float";
  default: number;
  min: number;
  max: number;
};

export type Algorithm = {
  id: string;
  label: string;
  description: string;
  params: ParamSpec[];
};

export type Environment = {
  id: string;
  label: string;
  description: string;
  algorithms: string[];
};

export type Preset = {
  id: string;
  label?: string;
  description?: string;
  // Exactly one catalog preset is the flagship default the composer pre-selects.
  default: boolean;
  environment: string;
  algorithm: string;
  params: Record<string, number>;
};

export type Catalog = {
  environments: Environment[];
  algorithms: Algorithm[];
  presets: Preset[];
};

export type ResolvedConfig = {
  environment: string;
  algorithm: string;
  params: Record<string, number>;
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
  trainable: false;
  reason: "custom-training-not-enabled";
};

export class ApiError extends Error {
  status: number;
  fieldError: FieldError | null;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "request failed");
    this.status = status;
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
  catalog: () => request<Catalog>("/training-options"),
  submitJob: (body: {
    preset?: string;
    environment?: string;
    algorithm?: string;
    params?: Record<string, number>;
  }) => request<Job>("/jobs", { method: "POST", body: JSON.stringify(body) }),
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
};

export const LIFECYCLE = ["queued", "starting", "training", "finalizing", "rendering", "evaluating", "completed"];
export const TERMINAL = new Set(["completed", "failed"]);
