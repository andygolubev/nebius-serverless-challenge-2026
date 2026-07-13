# saas-job-customization Specification

## Purpose
Let authenticated tenants configure what they train — environment, policy algorithm, and bounded
hyperparameters — validated server-side against a single catalog that also drives the UI, while
keeping presets as named shortcuts and never accepting arbitrary code.
## Requirements
### Requirement: Training options catalog
The system SHALL expose `GET /training-options` as the production-executable source of truth for the frontend composer. Every returned environment/algorithm combination and preset MUST resolve to a production `JOB_SPEC`; entries without an immutable runtime selection, training config, GPU platform/preset, timeout, and bounded parameter mapping SHALL NOT be returned or accepted by `POST /jobs`. The public catalog SHALL contain only GPU-accelerated MJX/JAX PPO workloads and SHALL exclude SB3 workloads even when their compute shape includes a GPU.

#### Scenario: Catalog contains only executable GPU workloads
- **WHEN** a client requests `/training-options`
- **THEN** every returned option resolves to an MJX/JAX PPO production job spec on an allowlisted GPU platform and can be submitted without a missing-spec failure

#### Scenario: Unsupported combination is hidden and rejected
- **WHEN** an environment/algorithm combination has no production job spec
- **THEN** it is absent from `/training-options` and a direct `POST /jobs` request for it is rejected with 422 before a job record or remote resource is created

#### Scenario: SB3 is not publicly offered
- **WHEN** a client requests `/training-options`
- **THEN** no SB3 algorithm, environment-only SB3 option, or SB3 preset is returned

#### Scenario: Catalog lists environments and policies
- **WHEN** a client requests `/training-options`
- **THEN** the response enumerates the executable Go1 MJX/JAX PPO environment-policy combination, its three workload profiles, and bounded parameter constraints

### Requirement: Custom job submission
The system SHALL accept job submissions at `POST /jobs` containing an environment id, a policy configuration (algorithm plus optional hyperparameter overrides such as learning rate, total timesteps, seed), and optional run settings. The system SHALL validate every field against the catalog's allowlists and bounds server-side; unknown fields, unknown environments/algorithms, or out-of-range values SHALL be rejected with 422 and a field-level error message. Arbitrary code, images, or shell commands SHALL NOT be accepted.

#### Scenario: Valid custom job accepted
- **WHEN** an authenticated user submits an allowlisted environment with an allowlisted policy and in-range overrides
- **THEN** the system responds 201 with a queued job that records the full resolved configuration

#### Scenario: Out-of-range parameter rejected
- **WHEN** a submission sets a hyperparameter outside the catalog's declared bounds (e.g. total timesteps above the maximum)
- **THEN** the system responds 422 naming the offending field and the allowed range

#### Scenario: Unknown environment or policy rejected
- **WHEN** a submission references an environment or algorithm not in the catalog
- **THEN** the system responds 422 and no job is created

### Requirement: Resolved configuration on the job record
The system SHALL persist and return the fully resolved configuration (user overrides merged over defaults) on the job record so the user can see exactly what ran. Defaults applied by the server SHALL be visible in `GET /jobs/{id}`.

#### Scenario: Job shows resolved configuration
- **WHEN** a user fetches a job they submitted with only a learning-rate override
- **THEN** the response includes the environment, policy, the overridden learning rate, and the defaulted values for all other parameters

### Requirement: Backward-compatible presets
The system SHALL expose three named Go1 MJX/JAX PPO workload profiles using the verified H100 platform and immutable MJX runtime: `go1-mjx-quick`, `go1-mjx-standard`, and `go1-mjx-quality`. The profiles SHALL define increasing bounded workload sizes and complete server-owned execution settings, including total timesteps, checkpoint cadence, evaluation scope, rendered progression scope, and timeout. Exactly one profile SHALL be marked as the default. Existing Go1 preset aliases MAY be accepted during migration, but removed SB3 presets SHALL NOT remain publicly listed or create new production jobs.

The quality profile SHALL retain the verified 100,000,000-timestep workload. Quick and Standard values SHALL be chosen through bounded H100 acceptance runs so that their displayed duration/cost labels reflect observed end-to-end execution rather than timestep ratios alone.

#### Scenario: Three GPU workload sizes are listed
- **WHEN** a client requests `/training-options`
- **THEN** the response contains Quick, Standard, and Quality Go1 MJX PPO profiles with increasing workload sizes and user-facing duration/cost guidance

#### Scenario: Quality profile preserves the flagship run
- **WHEN** `go1-mjx-quality` is resolved
- **THEN** it selects Go1 MJX/JAX PPO on `gpu-h100-sxm` / `1gpu-16vcpu-200gb` with 100,000,000 total timesteps and the verified production runtime

#### Scenario: Removed SB3 preset is rejected
- **WHEN** a tenant submits a removed HalfCheetah or Ant SB3 preset
- **THEN** the system responds 422 and creates neither a SaaS job record nor a Nebius job

#### Scenario: Preset submission still works
- **WHEN** an authenticated tenant submits Quick, Standard, or Quality by preset ID
- **THEN** the system responds 201 and records the selected profile's fully expanded Go1 MJX configuration

#### Scenario: Catalog marks the flagship default preset
- **WHEN** a client requests `/training-options`
- **THEN** exactly one of the three GPU workload profiles is explicitly marked as the default

#### Scenario: Composer opens on the flagship preset
- **WHEN** an authenticated tenant opens the job composer
- **THEN** the default GPU workload profile is pre-selected and the tenant can select either of the other executable GPU profiles
