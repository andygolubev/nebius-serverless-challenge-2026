# MJX as flagship track: dedicated runtime image, per-spec image/platform, default preset

## Why

The MJX/JAX track (`go1` + `ppo-mjx`) is the project's flagship demonstration — thousands of GPU-parallel simulations — yet the SaaS runs every job from the single SB3 runtime image (`SIM2POLICY_JOB_IMAGE`), the composer opens on a blank preset, and SB3 jobs burn an H100 they cannot use (SB3 simulation is CPU-bound). CI only builds and publishes the `sb3` Dockerfile target, so there is no published MJX runtime image to run the flagship track on at all.

## What Changes

- CI builds, validates, and publishes the `mjx` target of `sim2policy/Dockerfile` alongside the existing `sb3` target, with its own immutable commit tag and a `mjx-runtime` compatibility tag.
- The SaaS job catalog's `JobSpec` selects a runtime image per (environment, algorithm) instead of one global image: SB3 specs keep the SB3 image, `go1/ppo-mjx` uses the new MJX image. The nebius settings contract gains an MJX image variable.
- The `go1-mjx-demo` preset becomes the flagship default: it is listed first in `/training-options` and the composer pre-selects it, so a new user's first click launches the MJX track.
- SB3 job specs are right-sized from `gpu-h100-sxm / 1gpu-16vcpu-200gb` to `gpu-l40s-a / 1gpu-8vcpu-32gb` (the smallest documented L40S preset, ample for SB3's small networks); `go1/ppo-mjx` keeps the H100 shape verified by the full go1 run.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `training-runtime-image-pipeline`: CI additionally builds/validates/publishes the MJX runtime image with the same immutable-tag-then-compatibility-tag discipline as SB3.
- `training-job-orchestration`: the nebius backend submits each job with the runtime image and compute shape declared by that job's catalog spec (per-spec image/platform), and the settings contract requires an MJX job image.
- `saas-job-customization`: the catalog exposes a designated default preset (`go1-mjx-demo`) that the UI pre-selects; preset ordering places the flagship first.

## Impact

- `.github/workflows/sb3-runtime-image.yml` (extended or joined by an MJX workflow) — new registry tags `sim2policy:mjx-<sha>` / `sim2policy:mjx-runtime`.
- `saas/backend/app/catalog.py` (JobSpec image/runtime field, SB3 platform/preset change, preset ordering/default flag).
- `saas/backend/app/settings.py` + `orchestration.py` (new `SIM2POLICY_MJX_JOB_IMAGE`, per-spec image selection).
- `saas/frontend/src/views/Composer.tsx` (default preset pre-selection).
- `saas-nebius` Secret on the cluster must gain the MJX image variable before the new backend rolls out (out-of-band, documented in tasks).
- Tests: `saas/backend/tests/test_orchestration_nebius.py` (H100 assertion), `test_jobs.py`, frontend composer behavior.
