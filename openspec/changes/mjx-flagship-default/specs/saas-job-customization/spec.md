## MODIFIED Requirements

### Requirement: Backward-compatible presets
The system SHALL keep presets available as named shortcuts that expand to a full environment + policy configuration; submitting `{"preset": "..."}` SHALL remain valid and be recorded as the expanded configuration. The catalog SHALL designate exactly one preset as the default (`go1-mjx-demo`, the MJX flagship track), SHALL mark it explicitly in the `/training-options` response, and SHALL list it first; the job composer UI SHALL pre-select the default preset on load while allowing the user to switch to any other preset or clear the selection.

#### Scenario: Preset submission still works
- **WHEN** an authenticated user submits `{"preset": "ant-demo"}`
- **THEN** the system responds 201 and the job's resolved configuration matches the preset's expansion

#### Scenario: Catalog marks the flagship default preset
- **WHEN** a client requests `/training-options`
- **THEN** the presets list contains exactly one entry flagged as the default, it is `go1-mjx-demo`, and it appears first in the list

#### Scenario: Composer opens on the flagship preset
- **WHEN** an authenticated user opens the job composer
- **THEN** the form is pre-filled from the default preset's environment, algorithm, and parameters, and the user can still select a different preset or edit any field before submitting
