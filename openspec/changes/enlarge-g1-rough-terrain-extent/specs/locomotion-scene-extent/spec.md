## ADDED Requirements

### Requirement: Scene extent must contain the configured task
A locomotion run configuration SHALL be rejected before submission when the distance the configured
command implies over the configured horizon exceeds the worst-case distance from the spawn point to
the edge of the scene's supporting geometry. The implied distance SHALL be computed as
`target_velocity × episode_length × ctrl_dt`, and the worst-case available distance SHALL be
computed over all spawn yaws the environment's reset can produce. A scene whose supporting geometry
is unbounded — such as a MuJoCo `type="plane"` floor declared with zero size — SHALL satisfy this
requirement unconditionally.

#### Scenario: Configured task does not fit the scene
- **WHEN** a locomotion configuration requests a command and horizon whose implied travel exceeds
  the worst-case spawn-to-edge distance of its scene
- **THEN** validation fails with a diagnostic naming the implied distance, the available distance,
  and the maximum command that would fit, and no GPU step is paid

#### Scenario: Configured task fits the scene
- **WHEN** the implied travel is within the worst-case spawn-to-edge distance
- **THEN** validation passes and the run proceeds unchanged

#### Scenario: Scene has unbounded supporting geometry
- **WHEN** the scene's floor is an unbounded plane
- **THEN** validation passes for any command and horizon without computing a spawn-to-edge distance

### Requirement: Server-owned scene overrides preserve terrain character
A server-owned scene override that changes the extent of a height field SHALL preserve the upstream
field's spatial resolution in metres per cell and its elevation amplitude exactly, and SHALL derive
its height data from the upstream asset rather than from a newly generated random field. The
override SHALL NOT modify the installed upstream package.

#### Scenario: Enlarged height field preserves difficulty
- **WHEN** a server-owned scene enlarges an upstream height field
- **THEN** the resulting field reports the same metres-per-cell resolution and the same elevation
  amplitude as the upstream field, and its cell values are drawn from the upstream asset

#### Scenario: Override leaves the pinned package untouched
- **WHEN** a server-owned scene override is registered
- **THEN** the installed upstream package files are unmodified and the upstream scene remains
  loadable under its original identity

### Requirement: Scene identity is recorded in run evidence
A run whose environment uses a server-owned scene override SHALL record the scene identity and its
extent in durable run metadata, so that evidence produced under different scene geometry is not
silently comparable.

#### Scenario: Run metadata is inspected
- **WHEN** a run using a server-owned scene override publishes its metadata
- **THEN** the metadata names the scene override and its height-field extent, resolution, and
  elevation amplitude
