## ADDED Requirements

### Requirement: Server-owned G1 rough-terrain scene
The MJX path SHALL register `G1ForwardRoughTerrain` against a server-owned rough-terrain scene whose
height field spans 60 m × 60 m (half-extent 30 m), built by tiling the pinned upstream
`hfield.png` 3 × 3 at the upstream spatial resolution of 7.812 cm per cell and the upstream
elevation amplitude of 0.05 m. The override SHALL be applied at environment registration through the
same reviewed mechanism that supplies the fixed-forward command and preserves the upstream
randomizer, and SHALL NOT edit the installed `mujoco-playground` package. `G1ForwardFlatTerrain`
SHALL continue to use the upstream flat scene, whose floor is an unbounded plane.

#### Scenario: Rough environment is registered
- **WHEN** the fixed-forward G1 environments are registered
- **THEN** `G1ForwardRoughTerrain` loads a height field of 768 × 768 cells with half-extent 30 m,
  reporting the same metres-per-cell resolution and elevation amplitude as the upstream 256 × 256
  field

#### Scenario: Rough terrain difficulty is unchanged per step
- **WHEN** the enlarged height field is compared against the upstream field
- **THEN** every cell value in the enlarged field appears in the upstream field, the resolution and
  amplitude match exactly, and the enlarged field is a whole-number tiling of the upstream field

#### Scenario: Flat environment is unaffected
- **WHEN** `G1ForwardFlatTerrain` is registered
- **THEN** it loads the upstream flat scene unchanged and no scene override is applied

#### Scenario: Upstream package stays pinned and unmodified
- **WHEN** the registration runs against `mujoco-playground` 0.2.0
- **THEN** the pinned version assertion passes, no file in the installed package is written, and
  `G1JoystickRoughTerrain` remains loadable with its original 20 m × 20 m scene
