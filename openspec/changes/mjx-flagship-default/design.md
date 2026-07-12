# Design: MJX flagship track

## Context

- `sim2policy/Dockerfile` already has both `sb3` and `mjx` stages sharing a `base`, but CI (`.github/workflows/sb3-runtime-image.yml`) only builds/publishes `sb3` as `sim2policy:<sha>` + `sim2policy:sb3-runtime`.
- The SaaS nebius backend reads one global image (`SIM2POLICY_JOB_IMAGE` → `NebiusSettings.job_image`) and every `JobSpec` in `saas/backend/app/catalog.py` runs on `gpu-h100-sxm / 1gpu-16vcpu-200gb`.
- The `go1-mjx-demo` preset exists in `PRESETS` and `("go1", "ppo-mjx")` has a `JobSpec`, but a launch today would run the MJX entrypoint inside the SB3 image, which lacks the `mjx` extra (jax, mujoco-playground) — it would crash at import.
- The composer (`saas/frontend/src/views/Composer.tsx`) opens with no preset selected; `catalog.serialize()` emits presets in dict-insertion order with SB3 demos first.
- Orchestration env comes from the out-of-band `saas-nebius` K8s Secret (`envFrom`, optional); settings philosophy is validate-everything-at-startup so a misconfigured pod fails readiness.

## Goals / Non-Goals

**Goals:**
- Publish a validated MJX runtime image with the same immutable + compatibility tag discipline as SB3.
- Route each catalog job spec to its own runtime image and compute shape; go1/ppo-mjx runs on the MJX image.
- Make `go1-mjx-demo` the flagship default in `/training-options` and the composer.
- Right-size SB3 specs to `gpu-l40s-a / 1gpu-8vcpu-32gb`.

**Non-Goals:**
- No new environments or algorithms; `ant/ppo-mjx` stays without a job spec (mock-only).
- No change to the hosted sim2policy API presets (`configs/training_presets.yaml`) or `jobs/submit.sh`.
- No frontend redesign beyond default-preset selection and ordering.

## Decisions

### 1. One workflow with a build matrix, renamed `training-runtime-images.yml`

Replace `sb3-runtime-image.yml` with a single workflow whose job matrixes over `target: [sb3, mjx]`. Each leg builds its Dockerfile stage, runs a target-specific import gate (`sb3`: gymnasium/mujoco/stable_baselines3/sim2policy; `mjx`: jax/mujoco/mujoco_playground/sim2policy), and on trusted pushes publishes an immutable tag plus a compatibility tag.

- *Why not a second copied workflow*: the disk-free step, buildx setup, login, and tag/push logic would be duplicated verbatim; a matrix keeps one source of truth and separate GHA cache scopes (`scope=<target>-runtime`) per leg.
- *Alternative considered*: keep the sb3 file untouched and add `mjx-runtime-image.yml` — rejected as pure duplication that will drift.

### 2. Target-prefixed immutable tags: `sb3-<sha>` and `mjx-<sha>`

The current immutable tag `sim2policy:<sha>` cannot distinguish two runtimes built from one commit. New scheme: `sim2policy:sb3-<sha>` and `sim2policy:mjx-<sha>`. Compatibility tags stay `sb3-runtime` and gain `mjx-runtime`. Nothing consumes the old immutable format programmatically (the SaaS secret points at a compatibility/pinned ref chosen by the operator), so this is a reporting-format change only.

### 3. `JobSpec.image_key` + second required settings field

`JobSpec` gains `image_key: str` (`"sb3"` | `"mjx"`). `NebiusSettings` gains `mjx_job_image` from a new required env var `SIM2POLICY_MJX_JOB_IMAGE`; `SIM2POLICY_JOB_IMAGE` keeps its name and remains the SB3 image (no rename, no secret migration for the existing key). `build_submission` picks `s.job_image` or `s.mjx_job_image` by the spec's `image_key`.

- *Why required, not optional-with-fallback*: falling back to the SB3 image reproduces today's silent-crash failure mode for MJX jobs. The repo's stated settings philosophy is fail-at-startup via readiness, and the flagship track must not be launchable into a broken image.
- *Rollout implication*: the `saas-nebius` Secret must gain `SIM2POLICY_MJX_JOB_IMAGE` **before** the new backend image deploys, or the pod fails readiness (deliberate, visible, and reversible — the old ReplicaSet keeps serving).
- *Alternative considered*: put full image refs in `catalog.py` — rejected; image references are deployment config (registry host differs per install), not catalog data.

### 4. Flagship default via explicit `default` flag, not just ordering

`serialize()` marks `go1-mjx-demo` with `"default": true` and lists it first; the composer applies the default preset on catalog load (user can still switch or clear). An explicit flag is self-describing for the frontend and future clients instead of "first item wins" convention, and keeps `POST /jobs {"preset": ...}` behavior unchanged.

### 5. SB3 on `gpu-l40s-a / 1gpu-8vcpu-32gb`

SB3 simulation is CPU-bound with small MLP policies; an H100 is idle cost. `gpu-l40s-a / 1gpu-8vcpu-32gb` is the smallest L40S preset already documented and used in `sim2policy/jobs/README.md`, so it is a known-good shape on this project. Timeouts and step caps are unchanged. `go1/ppo-mjx` keeps `gpu-h100-sxm / 1gpu-16vcpu-200gb`, the shape verified by the full go1 run in `docs/submission-checklist.md`.

### 6. Quality default and sampled GPU telemetry

The 500k verification run rounded to 819,200 Playground steps, spent 88 seconds in JIT, trained for roughly 21 seconds, and ended at reward 0.002. The default therefore becomes the previously verified 100M-step quality workload (102.4M effective steps in the pinned stack). SB3 keeps its 5M catalog ceiling while `ppo-mjx` accepts 100M.

Start/end `nvidia-smi` snapshots are retained for compatibility but are not representative. MJX training samples every two seconds, logs phase transitions and JAX devices, and writes schema-v2 runtime telemetry with phase durations plus sample count, active count, mean/max utilization, and peak memory. Old schema-v1 readers remain supported.

### 7. Automatic GitOps bump and live reconciler convergence

On a successful `main` image build, the SaaS workflow uses scoped `contents: write` permission to commit the immutable SHA tag to the kustomization. It refuses to push if `main` advanced beyond the build SHA and uses `[skip ci]` to avoid recursive builds. Tag and manual-dispatch builds publish images without changing production GitOps state.

Terraform already renders `SIM2POLICY_MJX_JOB_IMAGE` for rebuilt servers. The existing VM also needs its root-owned reconciler updated explicitly because cloud-init `write_files` is once-per-instance; changing user-data alone does not rewrite the live script.

## Risks / Trade-offs

- [MJX image is large; matrix doubles CI build time and runner-disk pressure] → each leg keeps the disk-free step and its own cache scope; legs run in parallel on separate runners, so wall-clock is bounded by the slower leg.
- [Pod fails readiness after deploy if the secret lacks `SIM2POLICY_MJX_JOB_IMAGE`] → ordered rollout documented in tasks (secret first, then app); failure mode is loud and non-destructive.
- [L40S may slow long `ant-quality` SB3 runs vs H100] → SB3 throughput is CPU-dominated; the 8h timeout is retained and the step cap is unchanged. If a real run proves too slow, bumping the preset is a one-line catalog change.
- [Composer default preset changes first-load behavior existing users may not expect] → the preset select shows the flagship explicitly and remains editable; no submission semantics change.

## Migration Plan

1. Land CI workflow; confirm `mjx-runtime` published (manual dispatch if needed).
2. Add `SIM2POLICY_MJX_JOB_IMAGE` to the `saas-nebius` Secret on the cluster (out-of-band, per `sim2policy/infra/nebius/README.md` conventions).
3. Deploy backend + frontend change; readiness gates on the new setting.
4. Rollback: revert app image tag — old code ignores the extra secret key; no data migration involved.

## Open Questions

- None blocking. If the L40S quota is unavailable in the project's region at deploy time, fall back to keeping SB3 on H100 (catalog one-liner) without holding up the MJX track.
