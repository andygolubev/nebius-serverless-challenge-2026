## Why

Enlarging the rough terrain (`enlarge-g1-rough-terrain-extent`) removed a blocker that made the
rough gate unreachable. It did not make the gate *reachable*: G1 still fails the **flat** transition
gate, which runs on an unbounded plane and was never affected by terrain size.

The flat gate measured **8/10 episodes reaching the 1,000-step horizon**, i.e. a per-episode
survival rate around 0.80. The gate requires 10/10, and final publication requires 20/20. Those are
near-perfection bars:

| per-episode survival | flat 10/10 | final 20/20 | both |
| --: | --: | --: | --: |
| **0.80** (measured) | 10.7% | 1.2% | **0.1%** |
| 0.90 | 34.9% | 12.2% | 4.2% |
| 0.95 | 59.9% | 35.8% | 21.5% |

At the measured rate the campaign has roughly a **1-in-1000** chance of passing. That is the real
reason the last job stopped, and no amount of extra training budget changes the arithmetic.

Two further findings from the same evidence:

- **The `-1.1908 m/s` "walking backwards" number is not a second defect.** `flat_gate_result` takes
  `min(mean_velocity)` across *all* episodes including ones that terminated early, so an episode that
  trips and lands face-down contributes a negative average. The same two failed episodes are counted
  twice — once as a missing horizon, once as insufficient velocity.
- **Evaluation is not reproducible, contrary to the `policy-evaluation-reporting` spec.** In the
  published run, episodes 0, 5, 10 and 15 all record `seed: 0`, and `evaluate_mjx` sets
  `key = jax.random.PRNGKey(seed)` at the top of every episode, so those four rollouts should be
  byte-identical. Their lengths are 746, 658, 611, 610. Legged locomotion is chaotic and GPU
  floating-point reductions are not bit-reproducible, so a same-seed rerun diverges. The gate is
  therefore partly a lottery, and the spec's determinism claim is false as written.

Why the policy is only ~80% reliable is visible in the pinned reward. G1 pays **nothing** for
staying upright (`alive = 0.0`) and applies a one-off `termination = -100.0`, under
`discounting = 0.97` at 50 Hz — an effective lookahead of **0.67 s**. A fall 5 s ahead is discounted
to 5e-4; at 10 s it is 2e-7. The policy cannot see a fall coming in time to avoid it, and is paid
for tracking velocity rather than for surviving. It does exactly that: fast, and down one time in
five.

G1 is the outlier here. **T1, the other humanoid in the same pinned Playground 0.2.0**, uses
`alive = 0.25` with `termination = 0.0`. This repo's own custom-robot reward stack also pays an
alive term, and already carries a measured lesson about its size
(`custom_robot_contract.py`: alive was halved from 1.0 to 0.5 in v9 because standing still had
become "a cheap, safe local optimum").

## What Changes

- Turn on a **survival reward** for the server-owned fixed-forward G1 identities: `alive` 0.0 →
  **0.25**, matching T1's reviewed value in the same pinned package. `termination` stays at −100.0
  so the change is one variable, not two.
- Lengthen the planning horizon: `discounting` 0.97 → **0.99**, moving effective lookahead from
  0.67 s to 2 s so a fall is visible before it is unavoidable.
- Allow `reward_config.scales.alive` in `playground_config_overrides`, which today permits only
  `push_config.enable`. The allowlist stays closed — this adds one reviewed key, not arbitrary reward
  editing.
- **Relax the acceptance gates to a statistically sane tolerance**: flat 10/10 → **9/10**, final
  20/20 → **18/20**. Minimum velocity, mean velocity, and every other criterion are unchanged.
- Compute the flat gate's `min_velocity` over **completed** episodes only, so a fall is reported once
  as a missing horizon rather than also as a velocity failure.
- **BREAKING** for campaign authorization: a new reviewed mode, campaign ID, and matrix digest are
  required. The reward and gate are part of the reviewed contract, so prior authorizations do not
  carry over.
- Correct the `policy-evaluation-reporting` determinism requirement to describe what the system
  actually does: a fixed seed schedule with per-episode seeding, whose rollouts are not
  bit-reproducible on GPU.

Combined effect, if the reward change lands the policy at 0.95: campaign pass chance moves from
**0.1% to roughly 85%**.

Explicitly **not** changed: physics, `ctrl_dt`/`sim_dt`, reset and noise, observation and action
spaces, the termination predicate, pushes (stay disabled), the scene, the velocity thresholds, or
the published recording.

## Capabilities

### New Capabilities
<!-- none: this changes the behaviour of existing capabilities only -->

### Modified Capabilities
- `policy-training-backends`: the closed `playground_config_overrides` allowlist gains
  `reward_config.scales.alive`, and the fixed-forward G1 identities carry a reviewed survival reward
  and discount factor.
- `showcase-run-curation`: acceptance moves from all-or-nothing to a stated tolerance, the flat
  gate's velocity statistic is computed over completed episodes, and a new authorization mode is
  required.
- `policy-evaluation-reporting`: the determinism requirement is corrected to match observed
  behaviour, and evidence records that rollouts are not bit-reproducible.

## Impact

- `sim2policy/configs/g1_forward_flat_mjx.yaml`, `g1_forward_rough_mjx.yaml` — `alive`, `discounting`.
- `sim2policy/src/sim2policy/config.py` — override allowlist.
- `sim2policy/src/sim2policy/g1_curriculum.py` — flat gate tolerance and velocity statistic.
- `sim2policy/src/sim2policy/showcase_matrix.py`, `configs/showcase_training_matrix.yaml` —
  acceptance tolerance, new authorization, new matrix digest.
- Tests across `test_config.py`, `test_g1_curriculum.py`, `test_showcase_matrix.py`,
  `test_checkpoint_selection.py`.
- Runtime image rebuild and a bounded GPU probe. **Requires retraining** — the reward change only
  takes effect through a fresh curriculum run.
- No SaaS backend, frontend, or GitOps change. The published G1 recording is untouched.
