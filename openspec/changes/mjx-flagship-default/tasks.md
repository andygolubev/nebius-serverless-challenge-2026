## 1. Runtime image CI (SB3 + MJX matrix)

- [x] 1.1 Replace `.github/workflows/sb3-runtime-image.yml` with `training-runtime-images.yml`: one job matrixed over `target: [sb3, mjx]`, keeping the disk-free step, buildx setup, PR-no-push gating, concurrency cancellation, and per-target GHA cache scopes (`<target>-runtime`)
- [x] 1.2 Add per-target import gates: sb3 → `import gymnasium, mujoco, sim2policy, stable_baselines3`; mjx → `import jax, mujoco, mujoco_playground, sim2policy` (verify the exact mjx extra's import names against `sim2policy/pyproject.toml`)
- [x] 1.3 Publish target-prefixed immutable tags `sim2policy:sb3-<sha>` / `sim2policy:mjx-<sha>` before updating compatibility tags `sb3-runtime` / `mjx-runtime`; report both refs and digests in the step summary
- [x] 1.4 Update the `training-runtime-image-pipeline` references in docs that mention the old workflow name or `sim2policy:<sha>` immutable format (grep `sb3-runtime-image` across README/ARCHITECTURE/sim2policy docs)

## 2. Per-spec runtime image in the backend

- [x] 2.1 Add `image_key: str` to `JobSpec` in `saas/backend/app/catalog.py` (`"sb3"` for the two SB3 specs, `"mjx"` for `go1/ppo-mjx`)
- [x] 2.2 Add required `SIM2POLICY_MJX_JOB_IMAGE` → `mjx_job_image` to `_REQUIRED` and `NebiusSettings` in `saas/backend/app/settings.py`
- [x] 2.3 In `build_submission` (`saas/backend/app/orchestration.py`), select the submission image from the spec's `image_key` (`job_image` vs `mjx_job_image`)
- [x] 2.4 Update backend tests: settings fixtures gain the new env var; add a test that a `go1/ppo-mjx` submission uses the MJX image and an SB3 submission uses the SB3 image; add a settings test that a missing `SIM2POLICY_MJX_JOB_IMAGE` fails validation

## 3. Right-size SB3 hardware

- [x] 3.1 Change both SB3 `JobSpec`s in `catalog.py` to `platform="gpu-l40s-a"`, `preset="1gpu-8vcpu-32gb"`; keep `go1/ppo-mjx` on `gpu-h100-sxm / 1gpu-16vcpu-200gb`; update the comment explaining the split
- [x] 3.2 Fix `test_orchestration_nebius.py` assertions (`gpu-h100-sxm`) to match the per-spec shapes

## 4. Flagship default preset

- [x] 4.1 Reorder `PRESETS` in `catalog.py` so `go1-mjx-demo` is first and mark it `"default": true` in `serialize()` (exactly one default)
- [x] 4.2 In `saas/frontend/src/views/Composer.tsx`, pre-select and apply the catalog's default preset when the catalog loads, keeping the select editable/clearable; update the frontend types in `api.ts` for the `default` flag
- [x] 4.3 Add/adjust backend tests for `/training-options`: default flag present on exactly one preset, `go1-mjx-demo` first
- [x] 4.4 Rebuild the frontend bundle into `saas/backend/static/` per the repo's existing build flow

## 5. Rollout

- [x] 5.1 Document `SIM2POLICY_MJX_JOB_IMAGE` in the `saas-nebius` Secret contract (deployment.yaml comment and/or `sim2policy/infra/nebius/README.md`) with the ordered rollout: publish `mjx-runtime` image → update secret → deploy app
- [ ] 5.2 Verify end-to-end after deploy: `mjx-runtime` tag exists in the registry, pod passes readiness, `/training-options` shows the default preset, and a `go1-mjx-demo` submission reaches Nebius with the MJX image and H100 shape
