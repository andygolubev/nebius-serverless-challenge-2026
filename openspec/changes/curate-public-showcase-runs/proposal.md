## Why

The public training gallery still contains placeholder run IDs. Historical acceptance artifacts prove
that six examples can succeed, but they do not satisfy the new objective: run a fresh, reproducible,
result-first campaign whose training progression is trustworthy and whose winning checkpoint can be
hardcoded as durable public evidence. G1 is the limiting case. A 25M run barely moved, and two later
200M no-push runs learned useful forward motion but still fell before the 1,000-step horizon in every
20-episode acceptance evaluation.

The campaign must be executable by a lower-cost agent without improvising hyperparameters, cloud
resources, retry policy, checkpoint selection, or acceptance decisions. The plan therefore needs an
explicit experiment matrix, a resumable state machine, machine-verifiable gates, and hard stop
conditions—not prose that asks the operator to “monitor and decide.”

## What Changes

- Replace the earlier reuse-first curation strategy with a fresh result-first training campaign for
  Reacher, HalfCheetah, Ant, Hopper, Walker2D, Go1, and G1. Historical passing runs remain immutable
  baselines and emergency fallbacks, not the default public pins.
- Add a server-owned campaign matrix containing exact algorithms, budgets, checkpoint intervals,
  training seeds, disjoint selection/final evaluation seeds, hardware, timeouts, hard acceptance
  floors, preferred showcase targets, and one bounded extension rule per example.
- Add a deterministic campaign runner and operator runbook. It serializes jobs, persists non-secret
  state, makes submission idempotent, verifies durable artifacts, selects checkpoints, classifies
  failures, performs cloud cleanup audits, and stops with `NEEDS_HUMAN` whenever the declared matrix
  cannot decide the next action.
- Make the shared host a control-and-edit terminal only. All executable preparation and workload
  activity—including dependency installation, tests, builds, container health/import checks,
  environment construction, smoke runs, artifact verification, evaluation, rendering, training,
  finalization, and campaign-runner execution—must occur on Nebius Cloud compute. The host may edit
  source/planning files, run non-executing Git/OpenSpec inspection, and issue authenticated control-
  plane or SSH commands that cause work to execute in Nebius; it may not execute project workload
  code or use local CPU/GPU for the campaign.
- Train the five SB3 examples on the validated CPU profile. Run three independent seeds, select the
  best checkpoint across seeds, and extend only the best seed once when the hard floor is met but the
  preferred showcase target is missed.
- Train Go1 directly on one H100 for three independent 200M-step seeds, select by full-horizon
  locomotion quality, and permit one 300M continuation of only the best seed when needed.
- Train G1 directly on one H100 with a maximum 450M-step flat-to-rough curriculum in one allocation:
  acquire a stable no-push flat gait by at most 200M steps, then spend the remaining budget on
  no-push rough-terrain robustness. Evaluate retained milestones and select the best checkpoint, not
  automatically the final checkpoint.
- Keep final acceptance strict: SB3 examples must pass their configured deterministic reward floor;
  Go1 and G1 must complete 20/20 deterministic 1,000-step episodes without falling and meet the
  per-episode minimum forward-velocity floor. Preferred targets are used for result quality but never
  weaken the hard publication gate.
- Pin a run only after immutable provenance, selected-checkpoint evidence, required checksummed
  artifacts, policy bundle, measured runtime/cost, public-schema compatibility, and cleanup audit all
  pass. Failed or merely artifact-complete runs stay private diagnostics.

## Capabilities

### New Capabilities

- `showcase-run-curation`: Deterministic, resumable, result-first training, checkpoint selection,
  acceptance, cleanup, and promotion of server-owned public showcase runs.

### Modified Capabilities

- `public-training-showcase`: Publish only accepted curated runs and derive displayed configuration,
  progression, runtime, cost, and hardware from their immutable evidence.
- `policy-evaluation-reporting`: Report selection-set and final-set checkpoint evidence, including
  explicit selected-checkpoint provenance and regressions.
- `rollout-media`: Bind initial, intermediate, selected, and final rollout media to exact evaluated
  checkpoints and labels.

## Impact

- **Planning and operations**: adds a detailed execution runbook, campaign matrix, resumable journal,
  exact robot run cards, retry/extension rules, cost/time envelopes, and handoff templates suitable
  for a lightweight execution agent. The runbook has an explicit Nebius execution-location gate.
- **Runtime** (`sim2policy/configs/`, `sim2policy/src/sim2policy/`, `sim2policy/jobs/`): will add
  server-owned result profiles, checkpoint selection/finalization, the G1 curriculum entry point, and
  a campaign CLI. These are implementation tasks; this proposal launches no jobs and changes no
  cloud resources.
- **Backend/frontend**: will replace placeholders only with independently accepted non-tenant runs
  and will expose measured progression evidence without restoring any public training action.
- **Cloud**: a reusable Nebius CPU D3 orchestration/builder machine performs every preparation,
  executable test, build, campaign command, and CPU workload; SB3 uses the validated `cpu-d3`
  profile; Go1 and G1 use the single-H100 profile because
  the operator explicitly prioritizes result and predictable wall time over minimum spend. Jobs are
  serialized and chargeable compute is stopped or deleted after durable evidence verification.
- **Compatibility/security**: public routes stay read-only, the artifact bucket stays private,
  tenant-shaped job identities remain forbidden, secrets never enter campaign state or Git, and
  existing tenant jobs remain unchanged.
