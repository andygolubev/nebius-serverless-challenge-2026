## 1. Survival reward

- [x] 1.1 Extend the `playground_config_overrides` allowlist in `config.py` from
      `{push_config.enable}` to `{push_config.enable, reward_config.scales.alive}`, keeping the
      closed-list rejection and its diagnostic for every other key
- [x] 1.2 Validate the `alive` override is a non-negative number, and reject a value at which
      standing still comes within 3x of walking under the config's `target_velocity`, using the
      pinned `tracking_sigma` and `tracking_lin_vel` scale
- [x] 1.3 Set `reward_config.scales.alive: 0.25` and `discounting: 0.99` in
      `configs/g1_forward_flat_mjx.yaml` and `configs/g1_forward_rough_mjx.yaml`
- [x] 1.4 Confirm the override actually reaches the environment: assert the constructed
      `G1ForwardFlatTerrain` / `G1ForwardRoughTerrain` report `reward_config.scales.alive == 0.25`
      (MJX-gated, runs where the MJX runtime is available)

## 2. Gate tolerance and statistics

- [x] 2.1 Change `g1_curriculum.flat_gate_result` to require 9 of 10 horizons instead of all, and to
      compute `min_velocity` over completed episodes only; keep the 0.4 m/s floor
- [x] 2.2 Return the horizon count and the completed-episode velocity minimum separately so a
      terminated episode is never reported as a velocity failure
- [x] 2.3 Move final acceptance from 20/20 to 18/20 in `showcase_matrix.py` and
      `configs/showcase_training_matrix.yaml`; leave `min_velocity` 0.4 and `mean_velocity` 0.6
- [x] 2.4 Add the assumed-reliability and computed-pass-probability fields to the authorization
      block, and fail planning when either gate's pass probability is below 50%

## 3. Evaluation determinism claim

- [ ] 3.1 Record in run evidence that rollouts are sampled, not bit-reproducible, alongside the
      deterministic seed schedule that was used
- [ ] 3.2 Remove any assertion or report text that claims same-seed rollouts reproduce

## 4. Tests

- [x] 4.1 `test_config.py`: `reward_config.scales.alive` is accepted; every other
      `reward_config.scales.*` key and every other Playground path is still rejected
- [x] 4.2 `test_config.py`: an `alive` value that would let standing still come within 3x of walking
      is rejected, with the margin named in the diagnostic
- [x] 4.3 `test_g1_curriculum.py`: 9/10 horizons passes, 8/10 fails; a terminated episode's negative
      mean velocity does not appear in the velocity statistic
- [x] 4.4 `test_showcase_matrix.py`: acceptance reads 18/20; an all-or-nothing gate is rejected; a
      gate whose computed pass probability is below 50% is rejected
- [x] 4.5 `test_checkpoint_selection.py`: ranking and acceptance agree with the new tolerance
- [x] 4.6 Confirm the six passing SB3 examples and the Go1 example are unaffected by the gate change

## 5. Validation before any campaign

- [ ] 5.1 Full builder gates: backend and frontend tests, TS/Vite build, strict OpenSpec, secret and
      large-file scans, `MUJOCO_GL=osmesa` for the MJX suite
- [ ] 5.2 Build the runtime image via the promotion workflow and run the bounded 1,000-step
      flat/rough contract probe
- [ ] 5.3 Propose the new authorization mode, campaign ID, and matrix digest for review, including
      assumed reliability and computed pass probabilities — **submit no job without that approval**

## 6. Reading the result

- [x] 6.1 On the approved run, stop at the flat gate and compute the observed per-episode survival
      rate from the flat selection evidence
      — `gallery-g1-survival-20260810-02` / `aijob-e00x87jgqn8ng9c44c`: 8/10 full horizons, 8/10
      no-fall, `min_velocity` 0.9145 m/s, gate `passed: false` (needed 9/10). Rough never funded.
- [x] 6.2 Compare against the 0.80 baseline and record it in `IMPLEMENTATION_LOG.MD`; if it has not
      moved, the survival-reward hypothesis is wrong and rough training should not be funded
      — observed 0.80, exactly the baseline: **it did not move**, so rough was not funded. Recorded.
      Velocity did improve markedly (0.9145 m/s minimum vs a 0.40 floor), so the `alive` bonus did
      not produce the stand-still failure it risked; only the survival half is unconfirmed.
- [x] 6.3 If it moved but fell short, evaluate `termination = 0.0` (T1's full shape) as the next
      single-variable change rather than adding training budget
      — **Implemented, with the precondition explicitly waived.** This task's stated trigger ("if it
      moved but fell short") was **not** met: survival did not move at all. The operator authorized
      proceeding to `termination = 0.0` regardless, on a fixed $18 budget. That is a defensible call
      — 10 episodes cannot distinguish 0.80 from a modest gain (Wilson 95% [0.49, 0.94]), and
      `termination` is the only remaining scale on which pinned G1 differs from T1 — but it is a
      **waiver, not a satisfied precondition**, and is recorded as such so the next reader does not
      infer that survival improved in `-02`. Still one variable: -100.0 -> 0.0, nothing else changed.
      Authorized as campaign `gallery-g1-survival-20260811-01`.
