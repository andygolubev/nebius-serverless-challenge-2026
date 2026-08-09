## Context

`enlarge-g1-rough-terrain-extent` fixed the rough scene. The flat transition gate is what actually
stopped the last campaign, and it runs on an unbounded plane, so terrain size never touched it.

Measured from the campaign's durable flat evidence: **8/10 selection episodes reached the horizon**,
min per-episode mean velocity −1.1908 m/s, `passed: false`, zero rough steps spent.

Three separate things are going on, and only one of them is the policy.

**1. The gate demands near-perfection.** At a per-episode survival rate `p`, an all-or-nothing gate
passes with probability `p^n`:

| p | flat 10/10 | final 20/20 | both |
| --: | --: | --: | --: |
| 0.80 (measured) | 10.7% | 1.2% | **0.1%** |
| 0.90 | 34.9% | 12.2% | 4.2% |
| 0.95 | 59.9% | 35.8% | 21.5% |

A coin-flip chance at 20/20 needs `p ≥ 0.966`. The measured 0.80 has a 95% confidence interval of
roughly [0.49, 0.94] on a 10-episode sample — wide, and its optimistic end still falls short.

**2. The velocity failure is the horizon failure, double-counted.**
`g1_curriculum.flat_gate_result` computes `min(mean_velocity)` over *all* episodes, including ones
that terminated. An episode that trips at second 3 and lands face-down averages backwards. The
−1.1908 is those same two failures wearing a second hat.

**3. Evaluation is not reproducible.** In the published run, episodes 0, 5, 10, 15 all record
`seed: 0`, and `evaluate_mjx` sets `key = jax.random.PRNGKey(seed)` at the top of each episode — so
those four rollouts should be identical. Lengths were 746, 658, 611, 610. MJX reductions on GPU are
not bit-deterministic and legged gait is chaotic, so a 1e-7 divergence at second 1 is a different
outcome by second 12. The `policy-evaluation-reporting` spec claims determinism it does not have.

Why `p ≈ 0.80`? The pinned G1 reward pays nothing to survive:

| scale | value | effect |
| --- | --: | --- |
| `alive` | **0.0** | no per-step reward for staying upright |
| `termination` | −100.0 | one-off −2.0 (×`dt`) at the moment of the fall |
| `discounting` | 0.97 @ 50 Hz | effective lookahead **0.67 s** |

A fall 5 s ahead is discounted to 4.9e-4; at 10 s, 2.4e-7. The critic cannot predict it, so the
−100 arrives as unpredictable noise rather than as a learnable signal. The policy is paid to track
velocity, and does: fast, and down one time in five.

G1 is the outlier in its own package. **T1, the other humanoid in pinned Playground 0.2.0, uses
`alive = 0.25` and `termination = 0.0`.** This repo's custom-robot stack also pays an alive term.

## Goals / Non-Goals

**Goals:**

- Give the policy a dense, learnable reason to stay upright, so `p` rises from ~0.80 toward ~0.95.
- Set gates a good policy can actually clear, given evidence that is sampled rather than exact.
- Stop double-counting one failure as two.
- Make the determinism claim in the spec true by weakening it to what the system does.

**Non-Goals:**

- Changing physics, `ctrl_dt`/`sim_dt`, reset/noise, observation or action spaces, the termination
  predicate, pushes, or the scene.
- Lowering the velocity bars. 0.4 m/s minimum and 0.6 m/s preferred mean are unchanged; only the
  count of tolerated failed episodes moves.
- Re-scoring or re-pinning the published recording.
- Making evaluation bit-reproducible. That is a much larger change (deterministic GPU reductions)
  and is not worth it to satisfy a gate that should tolerate sampling anyway.

## Decisions

### `alive = 0.25`, borrowed from T1 rather than invented

T1 is a humanoid, in the same pinned package, at the same version, tuned by the same authors. Using
its value is a reviewed number rather than a guess, and it is the single most defensible choice
available without a sweep.

**The risk is the standing-still trap**, and this repo has already measured it: `custom_robot_contract.py`
halved `alive` from 1.0 to 0.5 in v9 because "standing still collected alive + upright + height ≈ 2.6
per step for free while walking added at most 1.4 on top, so a dead stop was a cheap, safe local
optimum."

G1's reward shape makes that trap much shallower, and the margin is checkable in closed form.
`tracking_lin_vel` is `exp(-‖cmd − vel‖² / 0.25)` at scale 1.0:

| `alive` | walking pays | standing pays | ratio |
| --: | --: | --: | --: |
| 0.0 (today) | 1.000 | 0.077 | 12.9× |
| **0.25** | 1.250 | 0.327 | **3.8×** |
| 0.5 | 1.500 | 0.577 | 2.6× |

At 0.25 walking still pays nearly four times what standing pays, before `feet_air_time` (2.0) and
`feet_phase` (1.0), which pay only when actually stepping. The spec encodes this as a requirement
with a 3× floor, so the trap cannot be reintroduced by a later tweak.

Note that G1's `stand_still` cost does **not** help: `_cost_stand_still` multiplies by
`cmd_norm < 0.01`, so under a 0.8–1.0 m/s forward command it is identically zero. The tracking
reward is the only thing holding the robot to the task, which is exactly why the ratio above is the
number that matters.

**Alternative considered — set `termination = 0.0` as T1 does.** Rejected for now: it changes two
variables at once and destroys attribution if the run still fails. Worth revisiting if `alive` alone
is insufficient.

### `discounting 0.97 → 0.99`

This is the change that lets the critic see a fall coming: lookahead moves from 33 steps (0.67 s) to
100 steps (2 s). 0.99 is the standard value in legged RL; Playground's 0.97 is on the low side and
G1 does not override the package default. A dense `alive` reward and a longer horizon are
complementary — the first makes survival visible per step, the second makes it visible early enough
to act on.

Higher discounting raises advantage variance and can slow early learning. 0.99 is the conservative
end of the useful range; 0.995+ would be a bigger bet.

### Gate tolerance 9/10 and 18/20

Sampled, non-reproducible evidence cannot support an exact-count bar. With the tolerance:

| p | flat 9/10 | final 18/20 | both |
| --: | --: | --: | --: |
| 0.90 | 73.6% | 67.7% | 49.8% |
| 0.95 | 91.4% | 92.5% | **84.5%** |
| 0.97 | 96.5% | 97.9% | 94.5% |

18/20 at p = 0.80 is still only 20.6%, so a genuinely unreliable gait is still rejected — the
tolerance buys headroom for sampling noise, not for a bad policy. The added requirement that a gate
record its assumed reliability and computed pass probability, and fail below 50%, prevents the next
campaign being funded against arithmetic nobody checked.

### Exclude terminated episodes from the velocity statistic

A terminated episode already fails the horizon criterion. Letting its backwards average also fail
the velocity criterion reports one defect as two and obscures the diagnosis — it cost real time in
this investigation. Completed episodes are the only ones whose average velocity is meaningful.

## Risks / Trade-offs

- **The reward change does not move `p` enough** → this is a hypothesis about the cause, and it
  requires a paid run to test. Mitigation: the flat phase alone is ~50 min and ~$1.30, and the flat
  gate is measured before any rough step is spent, so a failed hypothesis costs one flat phase, not
  a full campaign. Measure `p` from the flat evidence and compare against 0.80 before continuing.
- **`alive` creates a standing-still policy** → guarded in closed form by the 3× margin requirement,
  and detectable immediately: the flat gate requires every completed episode to average ≥ 0.4 m/s, so
  a standing policy fails the gate rather than passing it quietly.
- **Relaxing gates reads as lowering the bar** → the public criterion text changes from "20/20" to
  "18/20", which is a real, visible weakening. The velocity bars do not move. The justification is
  that the evidence is a sample; requiring 20/20 from a non-reproducible measurement was never
  measuring what it claimed.
- **`discounting = 0.99` destabilizes PPO** → detectable in the flat phase as a worse gait, not just
  a worse gate. Rollback is a config revert; no artifact depends on it.
- **This is a training-contract change to a "pinned upstream" environment** → it is, and the spec
  said those settings stay unchanged. That requirement was written before the gate was known to be
  unreachable. The proposal changes exactly two scalars, both to values with precedent inside the
  same pinned package.

## Migration Plan

1. Land config, allowlist, gate, and tests. Inert until a G1 run is submitted.
2. Rebuild the runtime image (the promotion workflow added in `3922a27`) and run the bounded
   1,000-step flat/rough contract probe.
3. Propose the new authorization mode, campaign ID, and matrix digest for review, including the
   assumed reliability and computed pass probabilities the new requirement demands.
4. On approval, run the campaign. **Stop at the flat gate and read `p` off the flat evidence before
   letting rough training start** — that is the cheap test of this whole hypothesis.

Rollback is a config revert plus restoring the prior gate constants; nothing published depends on
either.

## Open Questions

- Is `alive = 0.25` enough, or is `termination = 0.0` (T1's full shape) also needed? Only a run
  answers this; the flat phase is the cheap place to find out.
- Should the flat gate sample more than 10 episodes? A 10-episode sample gives a ±20-point
  confidence interval on `p`, which is weak evidence for an expensive decision. More selection
  episodes cost GPU time but sharpen the estimate.
- The published recording remains the only artifact measured under the old reward, old scene, and
  old gate. It stays a verified recording, but it is not comparable to anything this change produces.
