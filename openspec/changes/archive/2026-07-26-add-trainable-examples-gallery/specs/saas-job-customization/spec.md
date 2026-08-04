## MODIFIED Requirements

### Requirement: Training options catalog
The system SHALL expose `GET /training-options` as the production-executable source of truth for
the frontend gallery. It SHALL publish exactly the seven accepted gallery examples and MAY expose
backward-compatible secondary Go1 workload sizes within the Go1 entry. Every returned example,
environment/algorithm combination, and profile MUST resolve to a production `JOB_SPEC`; entries
without an immutable runtime selection, training config, allowlisted platform/preset, timeout,
bounded parameter mapping, evaluation/render contract, artifact contract, and current acceptance
evidence SHALL NOT be returned or accepted by `POST /jobs`. The public catalog MAY contain
MJX/JAX and SB3 PPO workloads only through these server-owned entries.

#### Scenario: Catalog contains only executable gallery work
- **WHEN** a client requests `/training-options`
- **THEN** every returned entry resolves to a complete accepted production job spec and can be
  submitted without a missing-spec failure

#### Scenario: Unsupported combination is hidden and rejected
- **WHEN** an environment/algorithm combination has no accepted production job spec
- **THEN** it is absent from `/training-options` and a direct `POST /jobs` request for it is
  rejected with 422 before a job record or remote resource is created

#### Scenario: Accepted SB3 examples are publicly offered
- **WHEN** the seven-entry catalog is enabled
- **THEN** its five server-owned SB3 examples are returned with their accepted right-sized compute
  contracts and no arbitrary SB3 environment or preset is exposed

#### Scenario: Catalog lists exact examples and policies
- **WHEN** a client requests `/training-options`
- **THEN** the response enumerates Go1 Walker, Ant Explorer, HalfCheetah Sprint, Hopper Balance,
  Walker2D Stride, G1 Rough Terrain, and Reacher Target with one recommended bounded configuration
  apiece

### Requirement: Custom job submission
The system SHALL accept `POST /jobs` submissions containing a stable gallery example ID, or a
supported backward-compatible Go1 profile ID, plus only optional run settings and overrides
explicitly declared by that catalog entry. The system SHALL validate every field against catalog
allowlists and bounds server-side; unknown fields, examples, algorithms, or out-of-range values
SHALL be rejected with 422 and a field-level error. Arbitrary code, images, commands, environment
variables, secret selectors, and compute choices SHALL NOT be accepted.

#### Scenario: Valid gallery job accepted
- **WHEN** an authenticated user submits an accepted example with only in-range declared options
- **THEN** the system responds 201 with a queued job that records the gallery ID and full resolved
  configuration

#### Scenario: Out-of-range parameter rejected
- **WHEN** a submission sets an allowlisted field outside the selected entry's declared bounds
- **THEN** the system responds 422 naming the offending field and allowed range

#### Scenario: Unknown example or field rejected
- **WHEN** a submission references an entry outside the published catalog or supplies an
  undeclared option
- **THEN** the system responds 422 and no job is created

### Requirement: Backward-compatible presets
The system SHALL retain three named Go1 MJX/JAX PPO workload profiles using the verified H100
platform and immutable MJX runtime: `go1-mjx-quick`, `go1-mjx-standard`, and `go1-mjx-quality`.
The profiles SHALL define increasing bounded workload sizes and complete server-owned execution
settings, including total timesteps, checkpoint cadence, evaluation scope, rendered progression
scope, and timeout. `go1-mjx-quick` SHALL be the gallery's recommended Go1 configuration; Standard
and Quality SHALL remain secondary choices rather than separate gallery cards. Existing Go1 preset
aliases MAY be accepted during migration, but removed legacy SB3 preset IDs SHALL NOT remain
publicly listed or create new production jobs.

The quality profile SHALL retain the verified 100,000,000-timestep workload. Quick and Standard
values SHALL use bounded H100 acceptance evidence so displayed duration/cost labels reflect
observed end-to-end execution rather than timestep ratios alone.

#### Scenario: Three Go1 workload sizes remain available
- **WHEN** a client inspects the `go1-walker` training option
- **THEN** Quick is recommended and Standard and Quality are available as increasing secondary
  workload sizes with observed duration/cost guidance

#### Scenario: Quality profile preserves the flagship run
- **WHEN** `go1-mjx-quality` is resolved
- **THEN** it selects Go1 MJX/JAX PPO on `gpu-h100-sxm` / `1gpu-16vcpu-200gb` with 100,000,000
  total timesteps and the verified production runtime

#### Scenario: Removed legacy SB3 preset is rejected
- **WHEN** a tenant submits a removed HalfCheetah or Ant preset ID instead of the supported gallery
  example ID
- **THEN** the system responds 422 and creates neither a SaaS job record nor a Nebius job

#### Scenario: Go1 profile submission still works
- **WHEN** an authenticated tenant submits Quick, Standard, or Quality by profile ID
- **THEN** the system responds 201 and records the selected profile's fully expanded Go1 MJX
  configuration

#### Scenario: Gallery opens on examples
- **WHEN** an authenticated tenant opens the job composer
- **THEN** the seven examples are presented first and the Go1 card identifies Quick as its
  recommended bounded configuration
