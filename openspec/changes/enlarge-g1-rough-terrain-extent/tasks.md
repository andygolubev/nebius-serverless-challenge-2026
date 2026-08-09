## 1. Server-owned rough scene

- [ ] 1.1 Add the repo-owned scene XML as package data under `sim2policy/src/sim2policy/scenes/`, a
      copy of upstream `scene_mjx_feetonly_rough_terrain.xml` with the `<hfield>` line replaced by
      `<hfield name="hfield" nrow="768" ncol="768" size="30 30 .05 1.0"/>` and no `file` attribute;
      keep the include of `g1_mjx_feetonly.xml`, `sensor.xml`, the texture, and both keyframes byte-identical
- [ ] 1.2 Ensure the scene file ships in the wheel/image (package data in `pyproject.toml`) and add a
      test that resolves it via `importlib.resources` rather than a relative path
- [ ] 1.3 Add a helper that reads the pinned upstream `hfield.png`, normalizes it to 0–1, and returns
      the 3 × 3 tiled 768 × 768 array; assert the source is 256 × 256 and single-valued across RGB
- [ ] 1.4 Add `RoughTerrainScene` handling to `register_g1_forward_environments`: subclass
      `ForwardJoystick` so `G1ForwardRoughTerrain` calls `G1Env.__init__` with the repo-owned path,
      fills `mj_model.hfield_data`, reapplies the base post-load steps (`opt.timestep`, restricted
      joint range, offscreen buffer), re-runs `mjx.put_model`, then `_post_init()`
- [ ] 1.5 Leave `G1ForwardFlatTerrain` on the upstream flat scene and confirm no override is applied
      to it

## 2. Scene-extent invariant

- [ ] 2.1 Add a scene-extent descriptor (half-extent, cells per side, elevation amplitude, or
      "unbounded" for a zero-size plane) resolvable from a registered environment identity
- [ ] 2.2 Implement the feasibility check: reject when
      `target_velocity × episode_length × ctrl_dt` exceeds the worst-case spawn-to-edge distance,
      with a diagnostic naming implied distance, available distance, and the maximum fitting command
- [ ] 2.3 Wire the check into MJX run-config validation so every path (ad-hoc, pilot, campaign)
      is covered before any GPU allocation
- [ ] 2.4 Record scene identity, extent, resolution, and elevation amplitude in run metadata

## 3. Tests

- [ ] 3.1 `test_g1_forward_env.py`: registered `G1ForwardRoughTerrain` reports 768 × 768 cells,
      half-extent 30 m, resolution 7.812 cm/cell, and elevation amplitude 0.05 m
- [ ] 3.2 `test_g1_forward_env.py`: enlarged field is an exact 3 × 3 tiling — every 256 × 256 block
      equals the upstream array — and every cell value appears in the upstream asset
- [ ] 3.3 `test_g1_forward_env.py`: the installed playground package is unmodified after
      registration, and `G1JoystickRoughTerrain` still loads with half-extent 10 m
- [ ] 3.4 `test_config.py`: 0.8 m/s × 1,000 steps passes on the 30 m scene and fails on a 10 m scene;
      an unbounded plane passes for any command; the diagnostic names all three numbers
- [ ] 3.5 `test_showcase_matrix.py`: planning refuses `user_reviewed_rough_08_full_v2`, and requires a
      new mode, campaign ID, and matrix digest bound to the enlarged scene
- [ ] 3.6 Ranking rejects candidate sets whose runs report differing rough scene extents
- [ ] 3.7 Confirm the retained recording `showcase-gallery-g1-20260801-16-g1-s0-rough` is untouched:
      still curates as a verified recording with its original numbers

## 4. Matrix and authorization

- [ ] 4.1 Update `configs/g1_forward_rough_mjx.yaml` if the scene identity must be named there, and
      recompute the matrix digest
- [ ] 4.2 Add the new authorization mode and campaign ID to `showcase_training_matrix.yaml`, with
      `allowed_jobs: 1`, zero retries, zero extensions, superseding the exhausted rough-0.8 entry
- [ ] 4.3 Update `openspec/specs/showcase-run-curation/spec.md` and
      `openspec/specs/policy-training-backends/spec.md` at archive time, and add
      `openspec/specs/locomotion-scene-extent/spec.md`

## 5. Validation before any campaign

- [ ] 5.1 Run the full builder gates on the change: backend and frontend tests, TS/Vite build, strict
      OpenSpec, secret and large-file scans
- [ ] 5.2 Build the new `mjx-{git_sha}` image and run the bounded 1,000-step flat/rough contract probe
- [ ] 5.3 Run a GPU probe comparing MJX step time and peak memory on the 30 m scene against the 10 m
      scene; record both numbers in `IMPLEMENTATION_LOG.MD`
- [ ] 5.4 If step time regresses materially, stop and take the shrink-the-task fallback from
      `design.md` instead of proceeding
- [ ] 5.5 Replay the published checkpoint logging root `qpos[0:2]` at termination to confirm the
      terminations are edge-falls; record the result
- [ ] 5.6 Present measured probe evidence for a new authorization decision — **submit no campaign job
      as part of this change**
