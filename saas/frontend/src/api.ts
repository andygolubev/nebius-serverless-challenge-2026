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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = session.token;
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(path, { ...init, headers: { ...headers, ...init.headers } });
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
  return res.json();
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
};

export const LIFECYCLE = ["queued", "starting", "training", "finalizing", "rendering", "evaluating", "completed"];
export const TERMINAL = new Set(["completed", "failed"]);
