# Sim2Policy submission checklist

Verified on 2026-07-05 against the durable `go1-mjx-full-20260704` run.

## Deliverables

- [x] Repository: [andygolubev/nebius-serverless-challenge-2026](https://github.com/andygolubev/nebius-serverless-challenge-2026)
- [x] Immutable MJX image:
  `cr.eu-north1.nebius.cloud/e00rhramvvrnpvnc5d/sim2policy@sha256:3dbe8d4d59877884e150784f73b8619ba57ce37ae72df6861ac65100ae1ca3c8`
- [x] Final policy:
  `s3://sim2policy-artifacts/sim2policy/go1-mjx-full-20260704/checkpoints/final.zip`
- [x] Versioned final checkpoint:
  `s3://sim2policy-artifacts/sim2policy/go1-mjx-full-20260704/checkpoints/final-000102400000.zip`
- [x] Initial, mid, and final rollouts: `videos/untrained.mp4`, `videos/mid.mp4`, and
  `videos/final.mp4` beneath the durable run prefix.
- [x] Progression montage: `videos/progression_montage.mp4` beneath the durable run prefix.
- [x] 60-second demo recording: `videos/demo-recording.mp4` beneath the durable run prefix.
- [x] Metrics and benchmark report: `report/metrics.json`, `report/report.md`, and
  `report/backend-comparison.md` beneath the durable run prefix.
- [x] Artifact manifest: `report/artifacts.json` beneath the durable run prefix.
- [x] Training logs: `nebius ai job logs aijob-e00z7km5vrxqcwgfnc --since 24h --timestamps`.
- [x] Finalization logs: `nebius ai job logs aijob-e00zzajd6q84enxqdp --since 24h --timestamps`.
- [x] Publication/read-back logs:
  `nebius ai job logs aijob-e00vwmvsk75m06sqfe --since 24h --timestamps`.

Durable run prefix:
`s3://sim2policy-artifacts/sim2policy/go1-mjx-full-20260704/`.

## Measured result

- Environment/backend: `Go1JoystickFlatTerrain` / MJX (JAX 0.6.2, MuJoCo 3.10.0).
- Compute: Nebius `gpu-h100-sxm/1gpu-16vcpu-200gb`, NVIDIA H100 80 GB HBM3.
- Effective steps: 102,400,000; final Brax training reward: 27.515.
- Training runtime used for cost reporting: 630.042 seconds; dated rate: USD 2.95/hour;
  estimated cost: USD 0.5163.
- Deterministic evaluation: 20 episodes over seeds 0–4, mean reward 31.4511 ± 1.9065,
  mean length 1,000.
- The configured success criterion was not met: mean forward velocity did not reach 0.5. This is
  reported without changing the criterion or discarding episodes; the policy nevertheless completed
  all episodes without falling and the requested training/evaluation/publication workflow completed.

## Reproduction

1. Provision the registry, bucket, and artifact identity with OpenTofu in
   `sim2policy/infra/nebius/`.
2. Build the `mjx` Docker target on a disposable CPU VM, push it, record its digest, and remove the
   builder. Do not build on H100 time.
3. Submit `sim2policy/jobs/submit.sh` with `configs/go1_mjx.yaml`, run ID
   `go1-mjx-full-20260704`, the immutable digest above, the H100 platform/preset, the configured
   subnet, a bounded timeout, and MysteryBox-backed S3 credentials.
4. Run `python -m sim2policy.finalize` against the same run ID to restore initial/quarter/final
   checkpoints, render progression media, evaluate the final policy, generate reports, and sync the
   completed manifest.
5. Confirm the object inventory and metrics by downloading them in a fresh job. The read-back job
   above verified non-empty checkpoints, all rollout videos, the montage, the 3,345,207-byte demo
   recording, reports, metadata, and periodic checkpoint continuity.

Local release verification: `uv run ruff check src tests`, `uv run mypy src`, and `uv run pytest`.
The final run passed with 90 tests; generated checkpoints, logs, videos, credentials, and state are
kept out of Git.
