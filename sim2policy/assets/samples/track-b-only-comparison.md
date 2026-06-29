# Track B-only benchmark sample

Track A is marked **not completed** because the MJX/JAX smoke gate must pass before publishing a
quadruped result. This is the expected honest fallback when only the dependable SB3 baseline exists.

| Backend | Environment | Success criterion | Seeds | Hardware | Runtime (s) | GPU util. | Cost |
|---|---|---|---|---|---:|---:|---:|
| sb3 | HalfCheetah-v5 | mean_reward >= 4000: false | 0,1 | Linux/NVIDIA GPU validation host / Ubuntu 24.04 | 12.34 | 0.0 | unavailable |
| mjx | not completed | MJX smoke gate not completed: false | unavailable | unavailable | unavailable | unavailable | unavailable |

Context: the SB3 row is a bounded smoke artifact-contract example and does not claim convergence.
Use real full-budget metrics for the final challenge submission.
