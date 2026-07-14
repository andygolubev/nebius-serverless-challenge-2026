## Context

The production SaaS currently exposes one Go1 MJX training family through three workload sizes.
The separate Bring Your Robot beta validates bounded MJCF uploads and environment drafts, but it
intentionally cannot submit training jobs. Training already produces durable reports, metrics,
checkpoints, and media, yet the product does not define one portable, user-facing takeaway.

This change adds a deliberately small gallery: seven server-owned examples that are visually
different, have known success criteria, and are executable through the existing tenant, Nebius,
and artifact boundaries. It does not turn the SaaS into a general environment or code execution
platform.

## Goals / Non-Goals

**Goals:**

- Publish exactly seven trainable example cards backed by accepted production job specifications.
- Give every example one recommended bounded configuration and measured time/cost guidance.
- Make the training outcome understandable in the browser without requiring a download.
- Offer one optional, integrity-checked policy bundle for simulator reuse and reproducibility.
- Keep tenant isolation, immutable runtimes, bounded execution, and cost-aware cloud validation.
- Carry the selected example identity through the Jobs list and compact result detail.
- Make the boundary between validated custom setup and trainable server-owned example explicit and
  give the custom-robot user a useful next action.
- Include one complex humanoid MJX flagship without making unverified H100 necessity claims.

**Non-Goals:**

- Training tenant-uploaded robots or environment drafts.
- Accepting uploaded meshes, environments, reward code, containers, or shell commands.
- Deploying a learned policy to a physical robot or claiming simulator-to-real compatibility.
- Providing a universal ONNX/ROS export or converting backend-specific checkpoints.
- Creating a community marketplace or an open-ended hyperparameter laboratory.
- Letting users select SB3 or MJX independently of the chosen example.
- Keeping any GPU or CPU VM running after its validation work is complete.

## Decisions

### 1. Use one stable, server-owned seven-entry catalog

The catalog will use stable example IDs and the following fixed task/runtime families:

| Example ID | Card | Environment | Backend | Production hardware policy |
| --- | --- | --- | --- | --- |
| `go1-walker` | Go1 Walker | `Go1JoystickFlatTerrain` | MJX/JAX PPO | H100 accepted shape |
| `ant-explorer` | Ant Explorer | `Ant-v5` | SB3 PPO | CPU or cheapest accepted L40S shape |
| `halfcheetah-sprint` | HalfCheetah Sprint | `HalfCheetah-v5` | SB3 PPO | CPU or cheapest accepted L40S shape |
| `hopper-balance` | Hopper Balance | `Hopper-v5` | SB3 PPO | CPU or cheapest accepted L40S shape |
| `walker2d-stride` | Walker2D Stride | `Walker2d-v5` | SB3 PPO | CPU or cheapest accepted L40S shape |
| `g1-rough-terrain` | G1 Rough Terrain | `G1JoystickRoughTerrain` | MJX/JAX PPO | Evidence-selected L40S or H100 shape |
| `reacher-target` | Reacher Target | `Reacher-v5` | SB3 PPO | CPU or cheapest accepted L40S shape |

Each entry owns its label, short story, original avatar path, expected outcome, backend badge,
hardware label, one recommended configuration, bounded optional fields, measured duration/cost,
success criteria, and production job-spec reference. This central catalog drives the API and UI.
It avoids seven separate frontend definitions drifting away from executable server behavior.

The existing Go1 Standard and Quality profiles remain accepted secondary workload sizes for
backward compatibility, but `go1-mjx-quick` is the gallery recommendation. They do not create
additional gallery cards. Legacy removed SB3 preset IDs remain rejected; the new stable gallery IDs
are the supported entry point.

### 2. Hide any example that lacks complete acceptance evidence

An entry is public only when it resolves to an immutable runtime, training configuration,
allowlisted compute shape, timeout, evaluation/render contract, artifact contract, and a recorded
acceptance result for that exact revision. The API omits an incomplete entry, and direct submission
returns 422 before local or remote creation.

This favors an honest smaller runtime catalog over cards that lead to missing-spec or broken
result paths. Release acceptance still requires all seven; partial visibility exists only as a safe
failure mode during rollout or rollback.

### 3. Keep customization intentionally bounded

The normal gallery flow submits the card's recommended configuration. Only fields explicitly
declared by that entry, such as run name or seed, may be changed within server-owned bounds. The
backend, image, environment, algorithm, command, hardware, secret selectors, and artifact prefix
remain server controlled.

This gives a realistic training choice without multiplying the validation matrix. A general
environment editor or arbitrary hyperparameter form would make the demo less reliable and is out
of scope.

### 4. Use MJX for Go1 and a complex G1 flagship, then select hardware from evidence

Go1 continues on its MJX/JAX H100 path. A fresh 5M Quick acceptance showed a stable standing
policy but did not meet the declared forward-velocity gate, so the gallery recommendation is the
smallest named Go1 workload that passes the corrected robot-frame, no-fall evaluation; Quick is
not published as verified merely because training and artifact generation complete. The generic
Gymnasium `Humanoid-v5` card is replaced by `G1JoystickRoughTerrain`, a complex Unitree G1 humanoid
task already shaped for the MuJoCo Playground/MJX training interface. It reuses the MJX image,
hosted trainer, checkpoint,
evaluation, rendering, and finalization families while receiving its own bounded configuration and
success criteria.

The first 25M G1 comparison learned forward motion but fell in every fixed-seed episode and is not
accepted. The replacement workload follows the pinned MuJoCo Playground v0.2 tuned G1 contract:
200M steps, 8,192 environments, 32 minibatches, 4 updates per batch, unroll length 20, entropy
cost 0.005, the privileged critic observation, and 20 evaluation points. These values live in the
immutable runtime config instead of being assembled from fragile nested command-line overrides.

No robot intrinsically makes H100 mandatory. G1 acceptance will first define the exact workload,
convergence threshold, maximum wall time, and cost-to-result gate, then run that immutable revision
on the smallest L40S candidate and the single-H100 candidate. The production job spec selects the
cheapest shape that passes every gate. The card may say `H100 required` only when L40S fails a
declared memory, convergence, wall-time, or cost-to-result gate and H100 passes; otherwise it names
the accepted cheaper shape without an inflated hardware claim.

The five SB3 examples use CPU or the cheapest validated L40S configuration after import, render,
bounded-training, and cost checks; they never consume H100 for routine training. Images are built
on the reusable CPU builder, tagged immutably, and promoted only after increasing-cost gates pass.

### 5. Store original avatars locally

Every card uses a small original same-origin SVG with an accessible text alternative. The assets
are versioned with the frontend and use no hotlinks or unreviewed third-party media. This keeps the
gallery fast, deterministic, and free from external asset availability or licensing surprises.

### 6. Define a browser-first result contract

A completed gallery job shows a compact outcome summary before raw data: status, example identity,
primary KPI and evaluation summary, runtime, estimated/actual cost, final rollout, checkpoint
identity, resolved configuration, and runtime versions. Nested diagnostic payloads live behind
expandable details.

The result page is sufficient to answer “did it learn, what ran, and what did it cost?” Users do
not need to download anything to inspect or replay training.

### 7. Produce one deterministic policy bundle as the optional takeaway

Gallery finalization produces `policy-bundle.zip` with this common envelope:

- `README.md` with evaluation/reproduction steps and a simulator-only compatibility warning;
- `manifest.json` with schema version, example/run identity, paths, sizes, and SHA-256 digests;
- `resolved-config.json`;
- `evaluation/metrics.json`;
- `runtime/versions.json` with backend, simulator, libraries, and immutable image identity; and
- `checkpoint/` containing the final backend-native checkpoint.

Archive member order, normalized timestamps, filenames, and serialization are deterministic so
the same finalized inputs yield the same bundle digest. The final rollout remains a separate
streamable/downloadable artifact rather than inflating the policy archive. The checkpoint is not
converted to a misleading universal format; compatibility metadata tells the user which runtime
can load it.

The bundle is a required finalized artifact for newly created gallery jobs. If it cannot be built
or validated, the job remains in finalization and eventually fails with phase `finalization`
instead of claiming a complete result with a broken download. Historical jobs remain readable and
may legitimately have no bundle.

### 8. Reuse tenant-authorized artifact delivery

The bundle is registered in the validated artifact manifest and downloaded through the existing
owned-job artifact route. The browser receives a safe filename through streaming or a short-lived
presigned URL. Clients never supply storage keys, and cross-tenant requests return 404.

### 9. Add example identity without breaking historical jobs

New jobs persist a nullable `gallery_example_id` alongside the fully resolved configuration.
Historical jobs keep `null` and render with their existing environment/profile label. This is an
additive migration and does not rewrite existing job or artifact records.

### 10. Treat custom robot validation as a completed check, not a pending training stage

The My Robots flow will distinguish `Model validated` and `Setup validated` from `Trainable`.
Saving a setup proves that its MJCF metadata, robot type, task compatibility, scene preset, and
bounded objects satisfy the beta contract. It does not run an adapter build or GPU acceptance and
does not schedule a background transition to trainable.

The current disabled “Training coming after GPU validation” control implies a next step that users
cannot initiate. It will be replaced with a non-interactive explanation: custom robot training is
not available in this beta because the robot has no accepted observation/action/reward adapter and
production job specification. An active **Train a verified example** link will open the gallery;
the saved custom setup remains available for a future adapter feature.

Adding automatic custom training was considered, but it would require compiling tenant MJCF into a
server-owned runtime contract, defining safe observations/actions/rewards/termination, validating
rollout stability, producing a production job spec, and expanding the cloud acceptance matrix. It
is therefore a separate future change rather than a fix hidden inside this reliable gallery scope.

### 11. Keep backend selection server-owned

Every gallery entry has exactly one accepted backend and production job spec. The card displays an
SB3 or MJX badge so the execution model is transparent, but users select the task—not the training
framework. Requests that attempt to override the backend or algorithm are rejected.

The catalog and API already model environment/algorithm compatibility, so adding a selector would
be mechanically small. Making it a reliable product would be large: every dual-backend entry needs
equivalent observation/action/reward/termination semantics, a second runtime and job spec,
backend-specific checkpoints/rendering, comparable evaluation, measured guidance, and independent
cloud acceptance. Offering both backends for all seven cards would double the primary acceptance
matrix from seven to fourteen paths without giving most users a clearer task choice.

A future **Compare engines** experience may expose two backends for exactly one environment only
after both adapters implement the same task contract and pass equivalent acceptance. It is not
part of this gallery release.

## Risks / Trade-offs

- **Seven acceptance paths increase release work.** Run local/import/render tests first, then one
  bounded end-to-end acceptance job per exact entry. Batch only on right-sized compute and remove
  all remote jobs/instances after artifact checks.
- **Some SB3 tasks may not converge in a demo-sized budget.** Give each entry an explicit,
  task-appropriate success threshold and calibrate one bounded recommendation. Hide an entry if its
  accepted revision cannot meet the gate rather than publishing optimistic copy.
- **G1 may not justify H100.** Benchmark the exact accepted workload on L40S and H100 and make the
  hardware label follow the declared gate instead of the desired marketing tier.
- **A backend selector would double validation work.** Keep backend selection in the server-owned
  card spec; consider one controlled comparison experience only as a separate future change.
- **Users may mistake weights for a robot-ready controller.** Put the matching simulator/runtime
  in both the UI and README and explicitly state that physical deployment needs separate adaptation
  and safety validation.
- **Bundle generation adds finalization work.** Exclude video, stream large checkpoints, cap member
  size/count, and validate the manifest before publication.
- **Backend-specific checkpoints reduce portability.** Preserve native fidelity and document the
  loader contract instead of promising a lossy or unverified universal export.
- **Measured guidance can become stale.** Bind measurements to job-spec/image revisions and do not
  show unverified estimates as observed values.
- **“Validated” may be mistaken for “trainable.”** Use distinct status language, remove the
  unreachable GPU-validation implication, and route users to examples that are actually accepted
  for training.

## Migration Plan

1. Add the nullable example identity, catalog schema, and bundle metadata additively.
2. Implement and test all seven server-owned configurations and original avatars behind a disabled
   gallery release flag, and add the honest My Robots-to-gallery handoff without altering saved
   custom assets.
3. Build immutable runtime images on the CPU builder, run increasing-cost acceptance gates for
   every exact job specification, and compare the exact G1 workload on L40S and H100 before fixing
   its production hardware label.
4. Record measured duration/cost and enable only entries with complete evidence; release requires
   all seven to be accepted.
5. Deploy through the existing GitOps path, validate card submission, lifecycle, compact results,
   video, and bundle download in the production browser, and retain the accepted SaaS job rows for
   user review.
6. Delete Serverless AI validation jobs and temporary instances, stop the reusable CPU builder,
   and audit disks, IPs, and temporary rules.

Rollback disables the gallery release flag and leaves existing jobs and bundles accessible through
their normal job detail. No database downgrade or artifact deletion is required.

## Open Questions

None. Existing artifact retention applies to policy bundles, and the first release intentionally
uses one recommended configuration per card.
