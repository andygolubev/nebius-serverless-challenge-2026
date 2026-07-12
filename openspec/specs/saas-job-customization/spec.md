# saas-job-customization Specification

## Purpose
Let authenticated tenants configure what they train — environment, policy algorithm, and bounded
hyperparameters — validated server-side against a single catalog that also drives the UI, while
keeping presets as named shortcuts and never accepting arbitrary code.
## Requirements
### Requirement: Training options catalog
The system SHALL expose `GET /training-options` describing what users can configure: the list of environments (e.g. halfcheetah, ant, go1), the list of policy algorithms/backends available per environment, and for each tunable parameter its type, default, and allowed range or enum values. The catalog SHALL be the single source of truth the frontend renders the job composer from.

#### Scenario: Catalog lists environments and policies
- **WHEN** a client requests `/training-options`
- **THEN** the response enumerates environments, compatible policy options per environment, and per-parameter constraints (type, default, min/max or allowed values)

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
The system SHALL keep presets available as named shortcuts that expand to a full environment + policy configuration; submitting `{"preset": "..."}` SHALL remain valid and be recorded as the expanded configuration. The catalog SHALL designate exactly one preset as the default (`go1-mjx-demo`, the MJX flagship track), SHALL mark it explicitly in the `/training-options` response, and SHALL list it first; the job composer UI SHALL pre-select the default preset on load while allowing the user to switch to any other preset or clear the selection.

The default MJX preset SHALL request 100,000,000 timesteps, and the MJX algorithm's validation ceiling SHALL permit that value without raising the SB3 ceiling above 5,000,000.

#### Scenario: Preset submission still works
- **WHEN** an authenticated user submits `{"preset": "ant-demo"}`
- **THEN** the system responds 201 and the job's resolved configuration matches the preset's expansion

#### Scenario: Catalog marks the flagship default preset
- **WHEN** a client requests `/training-options`
- **THEN** the presets list contains exactly one entry flagged as the default, it is `go1-mjx-demo`, and it appears first in the list

#### Scenario: Composer opens on the flagship preset
- **WHEN** an authenticated user opens the job composer
- **THEN** the form is pre-filled from the default preset's environment, algorithm, and parameters, and the user can still select a different preset or edit any field before submitting
