## MODIFIED Requirements

### Requirement: Deterministic multi-seed evaluation
The system SHALL evaluate a checkpoint over a configurable episode count and seed set, defaulting to
20 episodes distributed across five seeds, seeding every episode from its declared seed, and SHALL
retain per-episode reward and length values. The seed *schedule* SHALL be deterministic and
recorded. The resulting rollouts SHALL NOT be claimed to be bit-reproducible: MJX reductions on GPU
are not bit-deterministic and legged locomotion is chaotic, so re-running the same seed on the same
checkpoint can produce a different episode length and outcome. Evidence SHALL therefore be treated
as a sample rather than an exact measurement, and any gate read from it SHALL state a tolerance
rather than requiring an exact count of perfect episodes.

#### Scenario: Default evaluation completes
- **WHEN** a user evaluates a compatible checkpoint without overriding evaluation settings
- **THEN** the system runs 20 episodes across five seeds on the recorded deterministic schedule and
  records every episode result

#### Scenario: The same seed is evaluated twice
- **WHEN** one checkpoint is evaluated twice on an identical seed schedule
- **THEN** per-episode outcomes may differ, the difference is not treated as a defect, and no
  requirement or report claims the rollouts are reproducible

#### Scenario: A gate is defined against sampled evidence
- **WHEN** an acceptance or transition gate is defined over episode outcomes
- **THEN** it states an explicit tolerance for failed episodes rather than demanding that every
  sampled episode succeed
