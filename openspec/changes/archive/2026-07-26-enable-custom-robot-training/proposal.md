## Why

Bring Your Robot currently stops after structural validation, so a user can save an MJCF setup but cannot prove it works in simulation or train a policy from it. The product needs a deliberately narrow, trustworthy path from validated upload to a real SB3 training job and normal downloadable results without allowing uploaded code or building a container per robot.

## What Changes

- Add an explicit **Prepare for training** stage that promotes a validated robot/setup snapshot to a server-owned S3 input prefix, compiles it in the immutable MuJoCo/SB3 runtime, and performs bounded environment, simulation, render, and short-learning smoke tests on `cpu-d3`.
- Accept only declared biped or quadruped MJCF robots using the existing primitive-geometry upload contract, and only the V1 combinations Stand Balance or Walk Forward on Flat Arena or Ramp Course with no optional objects.
- Add a digest-bound preparation state machine. **Start training** is enabled only while the exact robot, setup, runtime, adapter, and preparation-profile fingerprint remains accepted.
- Run accepted setups with one fixed, server-owned `custom-ppo-quick` SB3 profile on an allowlisted `cpu-d3` preset. Users cannot select a backend, image, command, arbitrary object-storage key, hardware shape, hyperparameter, or secret.
- Reuse one immutable generic runtime image for preparation and training. Uploaded MJCF and normalized setup JSON are runtime inputs from the server-selected S3 prefix; no per-robot Docker image is built.
- Persist preparation attempts and custom-job provenance, then produce the normal evaluation, metrics, rollout video, checkpoint, resolved configuration, and a downloadable policy bundle containing the exact robot XML and normalized setup.
- Clearly label the bundle as a simulator-only SB3 policy artifact, not a controller that can be deployed directly to a physical robot.
- Keep saved setups outside the V1 training matrix valid for editing and future use, but explicitly ineligible for preparation/training.

## Capabilities

### New Capabilities

- `custom-robot-training-preparation`: Eligibility rules, immutable input promotion, bounded preparation jobs, fingerprints, acceptance/failure states, and retry/invalidation behavior.
- `custom-robot-sb3-runtime`: Generic server-owned environment adapter, Stand Balance and Walk Forward task contracts, fixed `custom-ppo-quick` training, evaluation, and safety boundaries.
- `custom-robot-policy-bundle`: Required custom-job artifacts and simulator-only export contents, integrity, provenance, and disclosure.

### Modified Capabilities

- `saas-data-persistence`: Persist tenant-scoped preparation attempts, accepted fingerprints, and custom-job provenance across restarts.
- `saas-nebius-orchestration`: Safely add allowlisted CPU preparation and SB3 training job specifications without weakening the existing server-derived submission boundary.
- `saas-web-ui`: Add preparation eligibility/status, retry, Start training, job navigation, and clear simulator-only result messaging.
- `saas-artifact-access`: Include and securely deliver the required custom policy bundle and custom-job result artifacts through normal tenant-authorized controls.

## Impact

- Affects the SaaS API/domain model, SQLite migrations, object-storage input and artifact manifests, Nebius orchestration adapter, generic SB3 runtime, result finalization, and React robot/setup/jobs/results views.
- Depends on the Bring Your Robot validation and setup contracts and reuses normal SaaS job/result primitives; it does not turn arbitrary uploaded files into code or public gallery catalog entries.
- Adds bounded `cpu-d3` Serverless AI work. Exact preparation/training preset, time limit, and fixed PPO budget must be benchmarked and then allowlisted before production enablement.
- Requires two repository-owned canonical upload robots (one biped and one quadruped), negative security fixtures, local/mock coverage, and browser-driven production acceptance while preserving SaaS job records for user review.
