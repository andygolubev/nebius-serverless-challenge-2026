## ADDED Requirements

### Requirement: Catalog-driven complete scenario inventory
The validation suite SHALL derive its case inventory from the canonical sample metadata, serialized environment catalog, and custom-training eligibility contract while retaining independent invariants for the currently accepted robot types, compatibility edges, scenes, objects, capacity, and preparation eligibility. Every server-advertised discrete choice and every visible My Robots control MUST map to at least one stable case identifier, and an unmapped addition or removal MUST fail with an actionable coverage diagnostic.

#### Scenario: Current catalog inventory is generated
- **WHEN** the suite inventories the current two robot types, compatible tasks, four scenes, and four optional object types
- **THEN** it generates all 20 compatible no-optional-object robot/task/scene cases, all 80 corresponding single-default-object cases, retains the 8 historical V1-eligible combinations as anchors, and requires all 100 catalog-valid cases to be preparation-admissible

#### Scenario: Catalog gains an uncovered choice
- **WHEN** a task, scene, object type, parameter, readiness state, or mapped form control is added without a scenario mapping
- **THEN** the completeness gate fails and names the missing identifier or control

#### Scenario: Declared robot type paths are exercised
- **WHEN** canonical sample upload scenarios run through the Quadruped and Biped radio-control paths
- **THEN** each path asserts the contract-defined upload result and subsequent task filtering without inventing morphology inference outside the current upload contract

### Requirement: Exhaustive bounded validation at cheap layers
The backend and component suites SHALL exhaust every task compatibility edge, scene preset, object type, scene-specific capacity transition, and declared object parameter at its default, minimum, maximum, empty/non-numeric client state, and invalid out-of-bound values. Valid cases MUST persist the normalized server result; invalid cases MUST show or return the owning field diagnostic and MUST NOT persist a partial model or setup.

#### Scenario: Every compatible discrete setup is submitted
- **WHEN** the generated positive matrix runs against the API
- **THEN** every compatible robot/task/scene row with zero optional objects and with each single default optional object saves idempotently with the expected normalized objects, digest, and readiness reason

#### Scenario: Every numeric boundary is checked
- **WHEN** the suite exercises each position, rotation, and dimension parameter for Box, Ramp, Hurdle, and Step
- **THEN** defaults and inclusive endpoints are accepted, empty/non-numeric client input disables save, and just-outside or non-finite API values are rejected at the correct object field without persistence

#### Scenario: Scene-specific object capacity is reached
- **WHEN** optional objects fill Flat Arena, Ramp Course, Hurdle Course, or Step Course to six total objects
- **THEN** the sixth-total-object state is accepted, the browser prevents another addition, and a direct one-over-capacity API request is rejected without saving a setup

### Requirement: Every My Robots interaction is browser-verifiable
The browser suite SHALL verify the sample downloads; upload name, declared type, file, submission, and field errors; validated-model statistics, digest, download, delete, and Build environment actions; builder close, name, compatible task, scene, object add/remove, every parameter editor, review, save, and errors; saved-setup persistence and deletion; preparation, retry, and training-start states; and the verified-example handoff. It SHALL assert accessible roles/labels/states, keyboard operation, and usability at 375-pixel width.

#### Scenario: Valid upload reaches a complete saved setup
- **WHEN** a user downloads a canonical sample, uploads it through the normal form, builds a compatible setup, changes scene and object controls, and saves
- **THEN** the browser displays the validated model and normalized saved setup after reload with selections, counts, digest, and readiness explanation matching the API

#### Scenario: Invalid form state is corrected
- **WHEN** the user submits missing upload fields or enters an empty, non-numeric, or out-of-range object value
- **THEN** the owning accessible diagnostic appears, unrelated form state is preserved, and save remains unavailable until the value is valid

#### Scenario: Destructive confirmation is cancelled and accepted
- **WHEN** model or setup deletion is opened, cancelled, then confirmed for a resource created by the test
- **THEN** cancellation preserves the exact resource and confirmation removes it from normal list/detail views without affecting preexisting tenant data

#### Scenario: Preparation and start lifecycle is rendered
- **WHEN** controlled API responses project not-prepared, preparing, ready, failed, stale, quota, and idempotent-start states
- **THEN** the browser exposes only the valid Prepare, Retry, or Start action, disables duplicate submission, and shows sanitized state-specific guidance

### Requirement: Fast parallel execution with tenant-safe isolation
Independent cheap cases SHALL support deterministic parallel sharding and aggregate all case results. Each worker MUST use an isolated temporary database and tenant locally, or an independent dedicated test tenant for deployed mutations; otherwise deployed mutation MUST be serialized. Every case SHALL have a bounded timeout and target cleanup by exact IDs that it created.

#### Scenario: Parallel cheap matrix runs
- **WHEN** backend, component, or local-browser workers execute different stable case-ID shards concurrently
- **THEN** they share no mutable database, tenant, idempotency key, download path, or artifact path and produce mergeable results with no duplicate or missing case IDs

#### Scenario: Production tenant isolation is unavailable
- **WHEN** multiple deployed mutation workers would share one tenant and its model/setup quotas
- **THEN** the runner serializes mutations while allowing safe read-only checks and reports the reduced concurrency rather than racing shared state

#### Scenario: Cleanup fails
- **WHEN** a test-created model, setup, remote job, instance, disk, address, or temporary rule remains after its applicable cleanup phase
- **THEN** the run fails cleanup, reports the exact non-secret resource identity and safe next action, and MUST NOT report the environment clean

### Requirement: Production smoke and remote cost gates are explicit
The suite SHALL provide an opt-in deployed-browser mode for the configured SaaS base URL using a masked existing test-tenant session without logging credentials or model contents. The default deployed mode MUST verify catalog/UI agreement and safe upload, builder, persistence, and cleanup flows without starting remote preparation or training. Remote preparation and training SHALL require separate explicit gates, SHALL run only after cheaper gates pass, and SHALL be reported as `not-run-cost-gated` when not requested.

#### Scenario: Default production smoke runs
- **WHEN** an authorized operator runs the deployed suite without remote flags
- **THEN** the runner verifies both upload radio paths, task filtering, every scene/object control, bounds, save/reload/delete, and readiness copy while creating no preparation or training job

#### Scenario: One remote preparation canary is enabled
- **WHEN** all cheap gates pass and remote preparation is explicitly enabled
- **THEN** the runner submits at most one eligible fixed-profile preparation, follows it to accepted or failed with bounded polling, records sanitized evidence, and audits provider resources afterward

#### Scenario: One remote training canary is enabled
- **WHEN** remote training is explicitly enabled for a current accepted fingerprint
- **THEN** the runner submits at most one fixed custom job with a fresh idempotency key, verifies the browser/API lifecycle and artifact-complete or sanitized-failure result, and completes the required cloud audit without leaving compute running

#### Scenario: Paid gates are skipped
- **WHEN** preparation or training flags are absent
- **THEN** the report marks those paths `not-run-cost-gated` and MUST NOT count them as passed coverage

### Requirement: Failures drive regression-first repairs
Every product failure discovered by the matrix SHALL receive a minimal automated regression scenario at the owning boundary before or with its repair. After repair, the affected case and shard MUST pass, followed by the complete cheap gate; deployed behavior MUST be rechecked when the repaired code is deployed. Transient infrastructure failures SHALL be classified separately and MUST NOT be hidden by unbounded retries.

#### Scenario: Product defect is found
- **WHEN** a case shows deterministic frontend, API, persistence, or runtime behavior that violates an existing requirement
- **THEN** the implementation adds a reproducing regression, repairs the owning boundary, reruns the focused case and complete cheap matrix, and records the observed before/after result

#### Scenario: Infrastructure failure interrupts a case
- **WHEN** authentication, deployment, provider availability, or network state prevents the product assertion from running
- **THEN** the case is reported as an infrastructure error with bounded retry evidence and is not mislabeled as a product pass or failure

### Requirement: Sanitized coverage and cleanup reporting
Each run SHALL emit an authoritative machine-readable report and a concise generated human-readable summary containing catalog fingerprint, stable case IDs, layer and shard, selected non-secret values, duration, pass/fail/skip/not-run status, sanitized diagnostics, created/deleted resource IDs, cleanup/audit result, and exact untested cost-gated paths. Reports, downloads, screenshots, and traces MUST be gitignored and MUST NOT contain bearer tokens, email codes, uploaded XML, authorization headers, credentials, secret selectors, storage keys, or raw provider responses.

#### Scenario: All cheap layers pass
- **WHEN** the backend, component, and local-browser matrices complete successfully
- **THEN** the merged report proves there are no duplicate or missing expected case IDs, lists complete catalog/control coverage and timings, and distinguishes any unrun deployed or paid gates

#### Scenario: Failure evidence is written
- **WHEN** a case fails
- **THEN** its report includes a deterministic reproduction command, expected and sanitized observed state, and safe artifact references without recording secrets or private model content

#### Scenario: Secret scan detects sensitive evidence
- **WHEN** a report or publishable artifact contains a credential, authorization header, email code, uploaded XML, secret selector, or storage key pattern
- **THEN** publication fails and the artifact is quarantined or removed before any handoff

### Requirement: Every valid builder setup is training-capable
Every setup accepted by the server-owned environment builder SHALL be admissible to bounded preparation and the fixed custom-training profile. Capability admission MUST follow robot/task compatibility, normalized scene/object validation, deployment enablement, lifecycle state, quotas, and current preparation fingerprint; it MUST NOT reject a catalog-valid saved setup as an unsupported task, unsupported scene, or unsupported optional-object combination.

#### Scenario: Previously unsupported terrain and objects are prepared
- **WHEN** either robot family saves a compatible task on Flat, Ramp, Hurdle, or Step terrain with any bounded combination of Box, Ramp, Hurdle, and Step primitives within the six-object total
- **THEN** the setup projects `not_prepared`, can enter preparation, and the server-owned runtime composes the exact normalized preset and custom primitives without accepting tenant code, meshes, plugins, files, or URLs

#### Scenario: Recover From Fall is prepared for a quadruped
- **WHEN** a quadruped setup selects Recover From Fall with any valid terrain/object configuration
- **THEN** preparation exercises bounded fallen-state resets, recovery reward and success criteria, evaluation, rendering, and checkpoint reload before training can become ready

#### Scenario: Incompatible task remains invalid
- **WHEN** a biped setup requests Recover From Fall directly or any setup contains an unknown or out-of-bounds catalog value
- **THEN** builder validation rejects the request without persistence and no preparation or training job is created

### Requirement: Expanded worlds remain deterministic and safe
The normalized setup and server-owned runtime contracts SHALL use a versioned closed schema containing only declared robot type, compatible task, known scene, and at most six fully normalized primitive objects. Every object number MUST be finite and within the catalog bound, fingerprints MUST change for material setup/runtime changes, and composed worlds MUST remain within existing compilation and resource limits.

#### Scenario: Exact scene fingerprint is stable
- **WHEN** the same robot digest, normalized setup, runtime image, adapter, reward, and preparation profile are submitted repeatedly
- **THEN** the normalized bytes and preparation fingerprint are identical and preparation reservation remains idempotent

#### Scenario: Primitive input is tampered after publication
- **WHEN** a normalized object has an unknown field/type/source, a missing parameter, a non-finite or out-of-bound number, or makes the total exceed six
- **THEN** the runtime rejects the input before MuJoCo compilation with a sanitized stable failure reason

### Requirement: Completed training is navigable and guarded
When a setup has a current or most recent custom training job, the My Robots UI SHALL expose that job's lifecycle/result without losing preparation readiness. A terminal completed job SHALL provide a result link, and starting another paid run SHALL require an explicit re-run confirmation while preserving server-side idempotency and quota behavior.

#### Scenario: Completed setup card is revisited
- **WHEN** a custom job for a ready setup completes and the user returns to My Robots
- **THEN** the setup card links to the completed job result and does not present an unguarded bare Start training action

#### Scenario: User confirms a re-run
- **WHEN** the user requests another run from a setup with a completed job and confirms the cost-bearing action
- **THEN** the UI submits one fresh idempotency key, disables duplicate submission, and navigates to the new job; cancelling creates no job
