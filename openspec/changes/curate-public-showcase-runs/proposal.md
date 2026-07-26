## Why

The new public showcase is intentionally empty because all seven run IDs are placeholders. Real
evidence already exists for six examples, while the G1 humanoid evidence shows that 25M steps is
far too short and that even the later 200M no-push policy still falls before the 1,000-step horizon;
publishing the tenant's latest completed row would therefore hardcode a bad demo rather than proof.

## What Changes

- Audit the retained, non-tenant acceptance prefixes and pin the five passing SB3 runs plus the
  passing 100M Go1 run instead of paying to reproduce already-valid evidence.
- Add a reproducible operator curation workflow that validates exact image/config provenance,
  evaluation success, required checksummed artifacts, policy-bundle contents, measured cost and
  runtime, and public-response compatibility before a run ID can replace a placeholder.
- Fix the showcase evidence adapter for real runtime schemas: canonical environment identities such
  as `Ant-v5`/`Go1JoystickFlatTerrain`, the existing `success.met` object, and measured values from
  the pinned run must be normalized without weakening integrity or tenant-isolation gates.
- Require a published card to point at a run that passed its predeclared task gate. Artifact-complete
  but below-threshold diagnostics remain private and cannot be described as verified examples.
- Add structured milestone evidence and labeled initial/mid/final rollout media so each public result
  demonstrates actual training progress rather than only showing one final video.
- Replace the failed G1 “just run longer” approach with a bounded ladder: evaluate every retained
  no-push checkpoint first; if none passes, run cheap immutable pilot candidates using
  stability-aware model selection and flat-to-rough locomotion curriculum; only then fund one fresh
  full candidate. Keep the 1,000-step, 20-episode, fixed-seed, forward-velocity/no-fall acceptance
  gate unchanged.
- Compare L40S and H100 only after the G1 training contract is frozen, choose on passing
  cost-to-result evidence, and stop or delete every temporary compute resource immediately after
  durable artifacts are verified.
- Hardcode the seventh run only after G1 passes. If the bounded ladder exhausts its budget without a
  pass, keep that card unpublished and record the blocker; do not lower the threshold, shorten the
  evaluation, or substitute the user's failed 25M job.

## Capabilities

### New Capabilities

- `showcase-run-curation`: Reproducible selection, training, acceptance, promotion, provenance, cost
  control, and cleanup contract for server-pinned public showcase runs.

### Modified Capabilities

- `public-training-showcase`: Publish only passing curated runs, consume real runtime identity and
  evaluation schemas, and derive displayed execution/runtime/cost evidence from the pinned run.
- `policy-evaluation-reporting`: Record deterministic checkpoint-level progress and the selected
  checkpoint so convergence and regression are measurable before publication.
- `rollout-media`: Bind progression videos to evaluated checkpoint steps and expose honest labeled
  initial/intermediate/selected rollouts for curated showcase runs.

## Impact

- **OpenSpec and operator workflow**: adds a curated-run acceptance matrix, bounded G1 experiment
  ladder, explicit cloud budgets, immutable revision rules, and cleanup/audit gates.
- **Runtime** (`sim2policy/configs/`, `sim2policy/src/sim2policy/`): may add one server-owned G1
  curriculum/profile, checkpoint evaluation/model selection, and progress metadata/media. No tenant
  hyperparameter surface is restored.
- **Backend** (`saas/backend/app/catalog.py`, `showcase.py`, `artifacts.py`): replaces placeholder
  pins with accepted non-tenant run IDs and normalizes real manifest/config/metric schemas while
  preserving the separate public resolver and private bucket.
- **Frontend** (`saas/frontend/src/views/Showcase.tsx`, `ResultPanels.tsx`): shows measured progress
  and selected-checkpoint evidence already supplied by the public API; it gains no training action.
- **Cloud**: reuses six durable accepted runs. Paid work is limited to bounded G1 evaluation/pilots
  and at most the frozen final/hardware comparison, using immutable images and the existing private
  artifact bucket. No new VM, secret, ACL, public prefix, or tenant job is introduced.
- **Compatibility**: public routes stay read-only and unauthenticated; custom-robot training remains
  the only tenant job-creation path. Existing tenant jobs, including the inspected user's failed G1
  and custom-biped results, remain private and unchanged.
