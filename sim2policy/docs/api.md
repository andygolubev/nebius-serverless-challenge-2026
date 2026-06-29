# Sim2Policy demo API

A thin HTTP layer that lets demo users start **predefined** training runs and fetch their
artifacts. The API validates input against a preset allowlist, generates a safe run id, persists
run metadata, and triggers an orchestration backend. It never trains itself and reads run
status/artifacts from durable storage (S3 in production, the local run tree for the mock backend).

## Running

```bash
uv sync --extra dev --extra api
make api                       # mock backend, 127.0.0.1:8000
# or: uv run sim2policy-api
```

Configuration is environment-driven:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SIM2POLICY_API_BACKEND` | `mock` | `mock` (no Nebius/GPU) or `nebius` |
| `SIM2POLICY_API_PRESETS` | `configs/training_presets.yaml` | preset catalog (allowlist) |
| `SIM2POLICY_API_RUNS_ROOT` | `runs` | local run tree root |
| `SIM2POLICY_API_TOKEN` | _(unset)_ | optional demo bearer token |
| `SIM2POLICY_API_SUBMIT_SCRIPT` | _(unset)_ | path to `jobs/submit.sh` (nebius backend) |
| `SIM2POLICY_S3_BUCKET` / `_PREFIX` / `_ENDPOINT` | _(unset)_ | enable S3 storage when bucket is set |
| `IMAGE`, `PLATFORM`, `PRESET`, `SUBNET_ID` | _(unset)_ | Nebius compute target (nebius backend) |

When a demo token is set, every endpoint except `GET /health` requires
`Authorization: Bearer <token>`.

## Endpoints

### `GET /health`

Always open. Returns service health and the active backend mode.

```json
{ "status": "ok", "backend": "mock" }
```

### `GET /training-options`

Returns only allowlisted (enabled) presets. Feature-flagged presets such as `go1-mjx-demo` are
omitted when disabled.

```json
{
  "presets": [
    {
      "name": "ant-demo",
      "description": "Ant PPO demo ...",
      "backend": "sb3",
      "environment": "Ant-v5",
      "algorithm": "PPO",
      "max_duration": "3h",
      "max_total_steps": 3000000,
      "expected_artifacts": ["final_policy", "metrics_json", "..."],
      "safe_params": {
        "seed": { "type": "int", "default": 0, "min": 0, "max": 2147483647 },
        "render_progress_video": { "type": "bool", "default": true }
      }
    }
  ]
}
```

### `POST /train`

Starts a run. Body fields beyond `preset` and the preset's declared safe params are **rejected**
(`extra="forbid"`) — arbitrary environment IDs, images, commands, code paths, or reward functions
cannot be supplied.

Request:

```json
{ "preset": "ant-demo", "seed": 42, "render_progress_video": true }
```

Response (`202`):

```json
{
  "run_id": "ant-demo-20260629-abc123",
  "status": "queued",
  "status_url": "/runs/ant-demo-20260629-abc123"
}
```

Errors: unknown/disabled preset, extra fields, or out-of-range safe params return `422`. A backend
launch failure returns `502` (and the run's `status.json` is marked `failed`).

### `GET /runs/{run_id}`

Returns run status and a progress summary read from `metadata/status.json`. Unknown run ids return
`404`; unsafe run ids return `400`.

```json
{
  "run_id": "ant-demo-20260629-abc123",
  "preset": "ant-demo",
  "status": "training",
  "created_at": "2026-06-29T12:00:00+00:00",
  "updated_at": "2026-06-29T12:03:00+00:00",
  "progress": { "phase": "training", "latest_checkpoint": "step-100000.zip", "latest_mean_reward": 1234.5 }
}
```

### `GET /runs/{run_id}/artifacts`

Returns artifact URLs from the run's `report/artifacts.json` manifest. Tolerates partial/incomplete
runs (returns only artifacts that already exist). On S3 storage the URLs are presigned and
time-limited; in local mode they are filesystem paths. Every URL is scoped to the run prefix and
never built from client input.

```json
{
  "run_id": "ant-demo-20260629-abc123",
  "status": "completed",
  "artifacts": {
    "final_policy": "...",
    "metrics_json": "...",
    "report_md": "...",
    "video_untrained": "...",
    "video_mid": "...",
    "video_final": "...",
    "progression_montage": "..."
  }
}
```

## Run status lifecycle

`queued → starting → training → rendering → evaluating → completed`, or `failed` from any phase.
Terminal states are `completed` and `failed`. The training job (or mock backend) maintains
`metadata/status.json`; the API derives all responses from stored state.

## Storage layout

```text
<bucket>/<prefix>/<run_id>/
├── metadata/status.json        run-status lifecycle + progress
├── metadata/request.json       the validated demo request
├── checkpoints/                policy checkpoints
├── tensorboard/                TensorBoard logs
├── videos/{untrained,mid,final,progression_montage}.mp4
└── report/{metrics.json,report.md,artifacts.json}
```

## Security and limits

- Presets are an allowlist; only enabled catalog entries are accepted.
- No user code, environments, images, or reward functions are executed or accepted.
- Run ids are server-generated (`<preset>-<UTCdate>-<random>`) and pattern-validated.
- Each preset caps `max_total_steps` and job `max_duration`; requests cannot exceed them.
- Object keys are derived only from the run prefix and fixed layout, never from request input.
- Optional demo-token auth gates every endpoint except `/health`.

## Not in this phase

Custom environments, reward functions, policy architectures, user Docker images, multi-tenant
billing, production auth, and a required web UI are out of scope. See the change proposal under
`openspec/changes/add-serverless-training-api/` for future extension points.
```
