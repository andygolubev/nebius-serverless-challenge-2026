## Context

`sim2policy` trains G1 against `mujoco-playground==0.2.0`, pinned and asserted at registration in
[`g1_forward_env.py`](../../../sim2policy/src/sim2policy/g1_forward_env.py). That module already
establishes the reviewed override pattern: subclass upstream `Joystick`, replace exactly one
behaviour (`sample_command`), disable pushes, and re-attach the upstream randomizer by hand because
the public registration API does not expose it. This change extends that same pattern to the scene.

The rough scene, `scene_mjx_feetonly_rough_terrain.xml`, contains one worldbody geom:

```xml
<hfield name="hfield" file="assets/hfield.png" size="10 10 .05 1.0"/>
<geom   name="floor"  type="hfield" hfield="hfield" material="groundplane"/>
```

MuJoCo `hfield` `size` is `radius_x radius_y elev_z base_z`, so the ground is a finite 20 m × 20 m
patch with **nothing outside it**. The `home` keyframe spawns at `qpos = 0 0 0.83 …` and `reset()`
randomizes yaw, joint angles and velocities but never `qpos[0:2]`. The flat scene, by contrast,
declares `<geom name="floor" size="0 0 0.01" type="plane"/>` — size `0 0` is an unbounded MuJoCo
plane — which is why only rough is affected.

Measured properties of the shipped asset (`hfield.png`, 256 × 256, 8-bit RGB with identical
channels):

- spatial resolution `20 m / 256 = 7.812 cm` per cell
- elevation amplitude 0.05 m, spanning value range 0–254 (4.98 cm realised)
- **lag-1 spatial autocorrelation −0.0004 (x) and −0.0002 (y)** — the field is uncorrelated white
  noise, i.e. per-cell gravel, not rolling hills. Mean absolute step between adjacent cells is 85.2
  of 255 levels.

Loading goes through `G1Env.__init__`, which is convenient for an override:

```python
self._model_assets = get_assets()
self._mj_model = mujoco.MjModel.from_xml_string(
    epath.Path(xml_path).read_text(), assets=self._model_assets)
```

The XML is read as **text** from an arbitrary path, and assets are supplied as an **in-memory dict
keyed by bare filename** (`update_assets` does `assets[f.name] = f.read_bytes()`). A repo-owned
scene file placed anywhere on disk still resolves `g1_mjx_feetonly.xml`, `sensor.xml` and the
texture from that dict.

## Goals / Non-Goals

**Goals:**

- Make the rough acceptance gate physically satisfiable at the commanded 0.8 m/s over 1,000 steps.
- Keep per-step terrain difficulty provably identical, so the enlarged scene is not a quiet
  difficulty reduction that would weaken the public claim.
- Remove the unavoidable edge termination that injects unpredictable `termination = -100.0` penalties
  into training, given neither the policy nor the critic observation carries global position.
- Fail unsatisfiable configurations at validation time instead of after a paid campaign.
- Leave the pinned upstream package byte-identical.

**Non-Goals:**

- Changing rewards, PPO hyperparameters, physics, `ctrl_dt`/`sim_dt`, reset/noise, observation or
  action spaces, the termination predicate, or push settings.
- Changing acceptance thresholds. The gate stays 20/20 full horizons, ≥ 0.4 m/s, preferred mean
  ≥ 0.6 m/s.
- Re-pinning or re-scoring the published G1 card. It stays a verified recording.
- Fixing the flat-gate failure (min velocity −1.19 m/s, 8/10 horizons). That happened on an
  unbounded plane and is a genuinely separate defect.
- Deciding whether to spend a new campaign job. This change only makes one worth spending.

## Decisions

### Enlarge to 60 m × 60 m by 3 × 3 tiling, rather than stretching `size`

The naive fix — bump `size="10 10"` to `size="30 30"` and keep the same 256 × 256 PNG — **silently
makes the task easier**. It stretches the same bumps over 2.25× the area, cutting slopes to a third
at unchanged amplitude. That would trade an honest ⚠️ for a dishonest ✅.

Tiling the shipped asset N × N and scaling `size` by the same N preserves metres-per-cell exactly.
Verified in a prototype: base 7.812 cm/cell → tiled 7.812 cm/cell, elevation span 4.98 cm unchanged,
and tile (0,0) is bit-identical to tile (1,2).

Choosing N = 3 (half-extent 30 m, 768 × 768 cells):

| N | half-extent | cells | worst-case yaw | margin over the 16 m needed |
| --: | --: | --: | --: | --: |
| 2 | 20 m | 512² | 20 m | 25% |
| **3** | **30 m** | **768²** | **30 m** | **87%** |
| 4 | 40 m | 1024² | 40 m | 150% |

N = 2 is too thin: a walking gait curves, so path length exceeds net displacement — the published
run's worst episode covered 17.16 m of path. N = 3 absorbs that comfortably, supports up to 1.5 m/s
on the worst-case yaw if the command is ever raised, and costs 768² × 4 B ≈ 2.4 MB once at model
build.

**Alternative considered — generate a fresh larger noise field.** Rejected: it introduces a new RNG
and a terrain that was never reviewed, and it forfeits the ability to state that every cell value
came from the upstream asset. Tiling is the more defensible claim in review.

**Alternative considered — shrink the task instead (shorter rough horizon, or command ≤ 0.5 m/s).**
Rejected as the primary fix: both make the gate passable by making the demo weaker, and 0.5 m/s is
below the 0.6 m/s preferred mean the spec already commits to. Kept as the fallback if the enlarged
scene shows an unacceptable step-time regression.

### Tiling seams are safe here, and that is measurable rather than assumed

Tiling a correlated height field would create a visible ridge every 20 m. This field is uncorrelated
(lag-1 autocorrelation ≈ 0), and the wrap-around seam statistics are indistinguishable from internal
statistics — mean |Δ| 81.9/91.7 at the seam versus 85.2 internally, p95 198/215 versus 198, max
244/252 versus 254. A seam is therefore not detectable by the robot or by inspection.

Periodicity is separately unobservable within an episode: the tile period is 20 m and the robot
travels at most ~17 m, so it never re-encounters terrain it has already crossed.

### Declare the field by `nrow`/`ncol` and fill `hfield_data`, rather than shipping a tiled PNG

MuJoCo accepts an `<hfield>` declared with explicit `nrow`/`ncol` and no `file`, allocating a
zero-filled field that is then writable in place as `model.hfield_data`. Prototype confirms:
`hfield_nrow=768`, `hfield_ncol=768`, `size=[30, 30, 0.05, 1.0]`, `hfield_data.size == 589824`,
zero-filled before the write, and `mj_forward` succeeds after it.

This avoids committing a 1.5 MB generated binary to the repo and avoids injecting bytes into the
asset dict, which is populated inside `G1Env.__init__` and is awkward to pre-seed from a subclass.
The tiled array is derived at registration from the upstream PNG that is already on disk inside the
pinned package.

**Alternative considered — commit a pre-tiled `hfield_s2p_x3.png`.** Rejected: a committed binary
cannot be checked against upstream by inspection, whereas deriving it at load time makes the
"identical cell values" property a runtime assertion the tests can exercise.

### Rebuild the model in the subclass rather than patching playground globals

`Joystick.__init__` hardcodes `consts.task_to_xml(task)`, so the repo-owned XML path cannot be passed
through it. The subclass calls `G1Env.__init__` with the repo-owned path, then fills `hfield_data`
and re-runs `mjx.put_model`. This duplicates the base class's small set of post-load steps
(`opt.timestep`, restricted joint range, offscreen buffer size), which is a maintenance hazard in
general — but playground is pinned and the version is asserted at registration, so drift is caught
loudly rather than silently.

**Alternative considered — monkeypatch `g1_base.get_assets` or `consts.task_to_xml`.** Rejected:
global mutation of the upstream module is harder to review and leaks across environments. The
existing `locomotion._randomizer[name] = …` line is the one place the repo accepts this, and it is
narrowly scoped and commented; this change does not need to widen that precedent.

### Validate feasibility in config validation, not at campaign planning only

Putting the invariant in the run-config validator means every path — ad-hoc job, pilot, campaign,
custom robot — is covered, and the check runs before any GPU is allocated. Campaign planning then
inherits it for free. The check is a closed-form comparison of
`target_velocity × episode_length × ctrl_dt` against the worst-case spawn-to-edge distance
`min_yaw R / max(|cos yaw|, |sin yaw|)`, which for a square field is simply the half-extent.

## Risks / Trade-offs

- **The enlarged field changes MJX step time or memory on H100** → MuJoCo height-field collision only
  tests cells local to the contacting geom, so per-step cost should be flat, but this is the one
  claim not verifiable on the dev host. Mitigation: a bounded GPU probe measuring steps/sec and peak
  memory against the 20 m scene *before* any campaign is authorized, using the existing probe
  pattern (`aijob-e00mmdb67qcnm5af19` and siblings). Fallback is the shrink-the-task option.
- **A retrain still fails for an unrelated reason** → this change removes a proven blocker; it does
  not promise the gate will pass. The flat-gate failure is untouched and will still stop the
  campaign before rough training starts. Mitigation: fix or re-diagnose the flat gate before
  authorizing, and keep the flat gate's existing zero-rough-spend guarantee.
- **Evidence measured on the two scenes gets mixed** → a checkpoint that looked good on the 20 m
  scene is not comparable to one from the 60 m scene. Mitigation: the added
  `showcase-run-curation` requirement records scene extent in evidence and fails ranking across
  differing extents.
- **Reviewers read "bigger terrain" as "easier terrain"** → the difficulty-preservation property is
  the crux of whether this change is honest. Mitigation: it is asserted in tests (resolution,
  amplitude, and cell-membership against upstream), stated in the spec, and reproducible from the
  measurements in Context.
- **The published card's numbers become harder to interpret** → it will remain the only artifact
  measured on a 20 m scene. Mitigation: it stays labelled a verified recording with its original
  numbers; the spec forbids re-scoring it.

## Migration Plan

1. Land the scene override, invariant, and tests behind no flag — the change is inert until a G1
   rough run is submitted.
2. Rebuild the `mjx-{git_sha}` image; run the existing builder gates and the bounded 1,000-step
   flat/rough contract probe.
3. Run the GPU probe comparing step time and memory on both scene extents. If step time regresses
   materially, stop and take the shrink-the-task fallback instead.
4. Only then propose a new authorization mode, campaign ID, and matrix digest for review. No
   campaign job is submitted as part of this change.

Rollback is reverting the registration override: the upstream 20 m scene is untouched and
`G1JoystickRoughTerrain` remains loadable throughout, so nothing published depends on the new code
path.

## Open Questions

- Is the flat-gate failure (min velocity −1.19 m/s, 8/10 horizons on an unbounded plane) an
  independent defect, or does it share a cause with the rough failure? It must be understood before
  a campaign is worth authorizing, and it is out of scope here.
- Should `G1JoystickRoughTerrain` — the upstream identity the published recording used — also get an
  enlarged variant for like-for-like comparison, or is the retained recording's incomparability
  acceptable? Current spec text takes the latter position.
- Confirm empirically that the terminations are edge-falls: replay the published checkpoint logging
  root `qpos[0:2]` at termination. Cheap, needs no training, and would close the last inferential gap
  between "the robot must reach the edge" and "the robot dies at the edge".
