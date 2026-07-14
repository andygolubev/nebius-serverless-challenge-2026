## Context

The Bring Your Robot beta stores an immutable, structurally validated MJCF robot and a normalized setup made from a server-owned task template, scene preset, and bounded primitive objects. It intentionally returns `trainable: false`: MJCF does not define the observation vector, action mapping, reward, termination, evaluation rule, compute profile, or executable job specification.

This change adds that missing adapter for a narrow V1. A user first saves a setup and then asks the service to prepare it. Preparation is an asynchronous, bounded CPU job using the same generic MuJoCo/SB3 image that later trains the policy. Only a preparation accepted for the exact current input/runtime fingerprint can start a fixed `custom-ppo-quick` job. Custom jobs then use the existing tenant job lifecycle and result surfaces.

The important trust boundary is unchanged: the tenant supplies inert MJCF data and bounded catalog selections, never Python, a Dockerfile/image, a command, a reward function, a URL, a storage key, a secret, or a resource preset. MuJoCo compilation and simulation remain potentially expensive operations, so they occur in bounded worker jobs rather than the SaaS API process.

Official Nebius documentation lists `cpu-d3` presets from `4vcpu-16gb` upward and states that Serverless AI jobs use Compute platforms/presets. MuJoCo supports compiling XML to `mjModel`, and Stable-Baselines3 provides an environment checker for custom Gymnasium environments. Those mechanisms are useful gates, but they do not replace runtime limits, adversarial fixtures, or actual rollout/learning smoke tests.

## Goals / Non-Goals

**Goals:**

- Let an authenticated user move from a validated uploaded robot and saved V1 setup to preparation, a real CPU training job, normal results, and a self-contained simulator policy bundle.
- Support declared biped and quadruped primitive-geometry models for Stand Balance and Walk Forward on Flat Arena and Ramp Course, with no optional objects.
- Use one immutable generic SB3 runtime image and treat MJCF/setup documents as integrity-checked runtime input from a server-selected S3 prefix.
- Keep every image, entrypoint mode, adapter/reward version, task, scene, PPO value, platform, preset, timeout, storage prefix, and secret selector server-owned and allowlisted.
- Make acceptance, invalidation, retry, failure diagnosis, provenance, artifact finalization, and tenant isolation explicit and testable.
- Validate the complete support matrix with the repository's canonical biped and quadruped uploads and preserve production SaaS job rows and artifacts for user review.

**Non-Goals:**

- Per-robot Docker builds, arbitrary user code/plugins/includes/assets, mesh/texture/height-field upload, arbitrary scene objects, reward editing, hyperparameter editing, or backend/hardware selection.
- MJX/GPU training for uploaded robots in V1. MJX has a different compatibility surface and compilation/runtime risk; it can be proposed later after a separate compatibility gate.
- Recovery-from-fall, hurdle/step courses, optional catalog objects, multi-robot scenes, manipulation, sensors/cameras as policy observations, recurrent policies, curriculum learning, or training continuation/resume controls.
- Proving a user's declared morphology from names or topology, guaranteeing convergence for every accepted model, or exporting a controller that is directly deployable to physical hardware.
- Adding custom setups to the public `/training-options` gallery. A custom training action remains bound to one owned accepted setup.

## Decisions

### 1. Separate structural validation, training preparation, and learning success

The saved setup remains structurally `validated`. A derived `training_readiness` is one of `ineligible`, `not_prepared`, `preparing`, `ready`, or `preparation_failed`. Preparation attempts have their own durable lifecycle and remote identity. `ready` means the exact snapshot passed bounded compatibility and execution gates; it does not mean PPO will reach the task success threshold. Learning success appears only in the final evaluation.

Alternative considered: enable Start training immediately after upload validation. Rejected because XML structure alone does not prove that the composed model is dynamically finite, renderable, compatible with the generic adapter, or able to execute an SB3 learning/save/reload path.

### 2. Keep the V1 eligibility matrix smaller than the setup builder

Preparation accepts only:

- robot declaration: `biped` or `quadruped`;
- task: `stand-balance` or `walk-forward`;
- scene: `flat-arena` or `ramp-course`;
- `objects: []` from the user (the server-owned ramp is intrinsic to Ramp Course, not an optional object).

Existing Recover from Fall, Hurdle Course, Step Course, and optional-object setups remain valid saved drafts but show an explicit training-ineligible reason. They are not silently rewritten.

Alternative considered: expose every existing catalog combination. Rejected because each combination multiplies reward, termination, collision, convergence, and acceptance coverage, which conflicts with a dependable V1.

### 3. Promote exact immutable inputs; never accept a caller-selected object key

`POST /robot-setups/{setup_id}/preparations` resolves the owned active setup and robot in SQLite, computes a preparation fingerprint, and writes only these server-produced objects beneath `sim2policy/preparations/<preparation-id>/inputs/`:

- `robot.xml`: the exact validated UTF-8 XML;
- `normalized-setup.json`: canonical task/scene selection with no tenant objects;
- `input-manifest.json`: schema version, byte sizes, SHA-256 digests, robot/setup IDs and digests, robot declaration, runtime image digest, adapter/reward schema versions, and preparation profile version.

The preparation and training submissions receive an opaque preparation/run identity plus server-resolved configuration. They never receive a key, URL, command, or image from the request. The runtime resolves the expected prefix, rejects traversal, downloads with bounded sizes, and verifies every digest before compilation. A custom training run snapshots the accepted input documents beneath its own `sim2policy/<run-id>/inputs/` prefix so later robot/setup soft deletion cannot break historical results.

Alternative considered: let the worker download the original XML from an API or arbitrary S3 URL. Rejected because it introduces mutable inputs, SSRF/key-selection risk, and weak provenance.

### 4. Fingerprint acceptance and invalidate on every material change

The fingerprint hashes the robot digest, normalized setup digest, immutable runtime image digest, adapter/reward schema versions, and preparation-profile version. Repeating Prepare for an identical fingerprint returns the active or accepted attempt rather than launching a duplicate. A changed input, runtime, adapter, reward, or preparation profile produces a new fingerprint and makes the prior acceptance unusable for new training.

Retries after a terminal preparation failure create a new attempt tied to the same fingerprint so operational failures are distinguishable from changed inputs. At most one non-terminal preparation exists per setup/fingerprint. Training requests require the latest accepted fingerprint and use an idempotency key/active-job guard to prevent double-click submissions.

Alternative considered: store `trainable=true` permanently on the robot. Rejected because compatibility belongs to a robot + task + scene + runtime contract, not to XML alone.

### 5. Compose a server-owned world with a restricted robot subtree

Preparation reparses the already-upload-validated document, applies stricter training-eligibility checks, and deterministically composes its single floating robot root into a versioned server-owned Flat Arena or Ramp Course. The server owns gravity, timestep bounds, floor/ramp geometry, lighting, cameras, reset distribution, contact defaults, episode length, reward, and termination. Tenant world-level floors, ramps, cameras, lights, and simulation overrides are not part of the executable scene.

The V1 adapter admits a finite bounded set of primitive collision geoms and a single free root. Training eligibility requires supported hinge joints and explicit finite motor control ranges for the action-producing actuators, finite positive mass/inertia after MuJoCo compilation, bounded state dimensions, and no unsupported model features. The precise allowlist is schema-versioned and reported by preparation. The declared morphology is product metadata; V1 does not claim to infer anatomy from joint names.

Alternative considered: execute the uploaded MJCF as an entire world. Rejected because duplicate floors, tenant simulation options, cameras/lights, and hidden world elements would make task semantics and safety non-deterministic.

### 6. Use one generic SB3 environment adapter and fixed task contracts

Each job has one robot-specific but deterministic vector space. The adapter records the ordered observation and action schemas in resolved configuration:

- observation: root height and orientation/gravity features, root linear/angular velocity in a documented frame, normalized actuated-joint position and velocity features, previous action, and the task target;
- action: one normalized `[-1, 1]` value per eligible motor actuator, mapped and clipped to its verified control range;
- reset: bounded, seeded perturbations around the compiled initial state;
- termination: fall/height/orientation limits, non-finite state, runaway position/velocity, or the fixed episode horizon;
- Stand Balance reward: uprightness and target-height terms with root-motion, action, and energy penalties;
- Walk Forward reward: target forward velocity/progress and uprightness with lateral/yaw, action, and energy penalties.

All coefficients, frames, clipping limits, thresholds, horizons, and success rules live in versioned server configuration and are included in the result. SB3's environment checker is run, but acceptance also requires real resets, bounded actions, random/zero rollouts, headless rendering, and a short PPO save/reload/evaluation cycle.

Alternative considered: ask the user to upload reward or environment code. Rejected because it changes inert data upload into arbitrary code execution and makes results incomparable.

### 7. Reuse one immutable runtime with two server-selected modes

One SB3 image pinned by digest contains MuJoCo, Gymnasium, SB3, the generic adapter, preparation entrypoint, training entrypoint, evaluation, rendering, artifact synchronization, and bundle construction. Preparation and training use different server-owned commands/modes and resource profiles but never rebuild the image for an upload.

The proposed starting shapes are `cpu-d3` / `4vcpu-16gb` for preparation and `cpu-d3` / `8vcpu-32gb` for `custom-ppo-quick`. Before production enablement, a bounded benchmark task must confirm or adjust those allowlisted presets, disk, timeout, vector-environment count, PPO steps, evaluation frequency, and retention settings against all eight canonical combinations. The selected values are then frozen in versioned profiles and shown as resolved, non-editable configuration. Preparation has a hard wall-time and phase-specific limits; training has a fixed total-step and wall-time budget.

Alternative considered: H100 or selectable SB3/MJX backends. Rejected for V1 because generic SB3 custom environments are CPU-oriented, a backend toggle doubles the compatibility surface, and upload validation cannot currently guarantee MJX feature support.

### 8. Use preparation gates that test the entire trusted path

The bounded worker performs, in increasing cost order:

1. input manifest and digest verification;
2. secure reparse and training-eligibility allowlist checks;
3. server-scene composition and pinned MuJoCo compilation;
4. finite dimension, mass/inertia, joint/actuator/control, and observation/action-space checks;
5. deterministic reset checks across server-owned seeds;
6. zero-action and bounded-random rollouts with non-finite/runaway/contact/time checks;
7. at least one headless render and media probe;
8. Gymnasium/SB3 environment checking;
9. a very short PPO learn, checkpoint save, clean reload, and deterministic evaluation;
10. a signed-by-content preparation report upload and finalization check.

Each phase has a sanitized public failure code and bounded detail. XML text, stack traces, storage keys, credentials, tenant identifiers, and raw provider responses are not returned or logged. Process/job timeout and memory/disk limits protect the API from compile or simulation resource exhaustion.

Alternative considered: compile in the FastAPI request. Rejected because a pathological model could consume API CPU/memory and make the synchronous upload endpoint unreliable.

### 9. Start training through a setup-bound endpoint, but persist a normal Job

The API adds:

- `POST /robot-setups/{setup_id}/preparations` to prepare or idempotently reuse the exact fingerprint;
- `GET /robot-setups/{setup_id}/preparations/latest` to inspect current status/report metadata;
- `POST /robot-setups/{setup_id}/training-jobs` to create a normal tenant Job from the latest accepted fingerprint.

This avoids making a private custom setup look like a public catalog option and avoids accepting `setup_id` as a free-form variant of the existing catalog `POST /jobs`. The resulting Job has `job_kind=custom-robot`, `backend=sb3`, `profile=custom-ppo-quick`, robot/setup/preparation references, immutable input digests, and the normal lifecycle. The orchestration adapter selects a typed allowlisted job spec (`custom_prepare` or `custom_train`) and still derives every execution field server-side.

At most one custom preparation and one custom training job per tenant may be active; configurable per-tenant start quotas and global capacity limits fail before remote creation with actionable retry guidance. These defaults keep the demo predictable and can be raised by operations without expanding the public request schema.

Alternative considered: add custom setups to `/training-options` and reuse `POST /jobs`. Rejected because gallery entries are public static catalog products, while custom inputs are owned resources requiring an accepted preparation.

### 10. Snapshot normal results and add a simulator-only bundle

Custom training is completed only after the final checkpoint, evaluation metrics/episodes, human-readable summary/reward curve, rollout MP4, resolved configuration/runtime versions, artifact manifest, and policy bundle are readable and valid beneath the run prefix. The bundle contains:

- the load-tested final SB3 checkpoint;
- exact `robot.xml`;
- canonical `normalized-setup.json`;
- resolved adapter/reward/profile configuration and ordered observation/action schemas;
- runtime/version and evaluation metadata;
- a checksummed bundle manifest and README with a prominent simulator-only/non-physical-deployment notice.

The bundle contains no credentials, tenant identifier, arbitrary absolute path, unvalidated extra file, or executable user content. Normal tenant-authorized manifest access and safe filenames apply. A bundle load smoke test in the same pinned runtime is a completion gate.

Alternative considered: provide only the raw SB3 checkpoint. Rejected because the policy is unusable or misleading without the exact model, task/scene contract, feature/action ordering, normalization, versions, and limitations.

### 11. Preserve historical evidence while handling deletion safely

Preparation attempts and jobs are tenant-scoped and survive SaaS restarts. Soft-deleting a robot/setup prevents new preparation or training but does not remove input snapshots, job rows, result manifests, or authorized historical downloads. Production acceptance must not delete the SaaS jobs or S3 results that the user needs to inspect. Temporary builder/VM resources are still stopped or deleted immediately after their work, and failed/active cloud resources are audited according to repository operations policy.

## Risks / Trade-offs

- **[A structurally valid robot may not learn in the quick budget]** → Preparation is described as execution compatibility, not convergence; evaluation reports success/failure honestly, and canonical examples establish the supported demo floor.
- **[A generic reward may produce undesirable behavior]** → Keep only two versioned shaped tasks, expose reward terms and evaluation criteria in resolved results, and use rollout video plus multi-seed evaluation.
- **[Declared biped/quadruped metadata may be wrong]** → Do not claim topology inference; enforce adapter/dynamics gates and return a specific preparation failure when the model cannot satisfy the contract.
- **[MuJoCo compilation or simulation can consume excessive resources]** → Retain strict upload limits, add compiled-model/dynamic limits, run out of process on bounded CPU jobs, and enforce phase and wall-clock timeouts.
- **[Changing runtime/reward code can make an old acceptance unsafe]** → Include immutable image and schema/profile versions in the fingerprint and require re-preparation for new jobs.
- **[S3 input snapshots duplicate small XML/config files]** → Accept the small storage cost for immutable provenance and historical reproducibility; enforce byte caps and lifecycle policy only for abandoned preparation attempts.
- **[CPU quick training can take longer than a gallery GPU demo]** → Benchmark the matrix, freeze one right-sized `cpu-d3` profile, show observed range without promises, cap concurrency, and avoid H100 cost for SB3.
- **[A new CPU job type could weaken the GPU-only submission invariant]** → Replace the single hard-coded invariant with typed, separately tested allowlisted job-spec validators; never introduce a generic tenant-defined submission object.
- **[Preparation may succeed while production artifact finalization fails]** → Keep preparation/training finalization distinct, use bounded retries, and gate terminal states on readable validated reports/manifests.

## Migration Plan

1. Add migrations and code behind `CUSTOM_ROBOT_TRAINING_ENABLED=false`; existing validated robots/setups keep their current public behavior while the flag is off.
2. Add the generic runtime, mock preparation/training flows, typed job specs, input/artifact schemas, and canonical fixtures. Publish the runtime once with an immutable tag/digest using the normal CPU builder workflow.
3. Run local/API/UI/security tests, then benchmark preparation and `custom-ppo-quick` across all eight canonical robot/task/scene combinations on temporary `cpu-d3` jobs. Freeze the passing presets and bounds in versioned server configuration.
4. Deploy the SaaS schema/API/UI with the feature disabled, verify migrations and normal gallery jobs, configure the immutable runtime digest, then enable for an internal tenant.
5. Perform browser-driven production acceptance: upload both sample XML files, save all V1 setups, click Prepare, wait for Ready, click Start training, inspect each retained job/result, play rollout video, and download/load-check the policy bundle. Preserve SaaS job rows and artifacts for user validation.
6. Enable generally only after quotas, reconciliation, failure sanitation, artifact durability, and cloud cleanup evidence pass.

Rollback disables new preparation/training starts while continuing reconciliation and tenant access for existing attempts/jobs. Schema additions remain backward-compatible. The immutable input/result snapshots are retained according to policy; no rollback rewrites or deletes historical rows.

## Open Questions

No product-scope question blocks implementation. The exact preparation and `custom-ppo-quick` CPU preset, disk, wall-time, vectorization, step budget, and observed duration/cost text are measurement outputs, not user choices; the implementation tasks must benchmark and freeze them before production enablement.
