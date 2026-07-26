## Context

`add-public-training-showcase` landed a safe read-only surface and deliberately left all seven
`SHOWCASE_RUNS` values as `pending-curated-run-*`. The publication path is therefore empty today.
The artifact bucket already contains dedicated, non-tenant acceptance prefixes for five SB3
examples and Go1. Those runs passed predeclared gates and retained checkpoints, metrics, reports,
resolved configuration, runtime versions, initial/mid/final rollout media, checksums, and policy
bundles:

| Example | Candidate source run | Observed gate |
| --- | --- | --- |
| Reacher | `gallery-reacher-3aa59b1-20260714a` | -7.779 mean reward, passes >= -10 |
| HalfCheetah | `gallery-halfcheetah-3aa59b1-20260714a` | 1672.368 mean reward, passes >= 1500 |
| Hopper | `gallery-hopper2m-3aa59b1-20260714a` | 1562.019 mean reward, passes >= 1000 |
| Ant | `gallery-ant-3aa59b1-20260714a` | 2869.711 mean reward, passes >= 1000 |
| Walker2D | `gallery-walker2d2m-3aa59b1-20260714a` | 3812.003 mean reward, passes >= 1800 |
| Go1 | `gallery-go1-quality-433f3f9-20260714a` | 20/20 full 1,000-step episodes, 0.965 m/s mean, passes |

Production tenant evidence confirms why no existing G1 row is suitable. The latest 25M gallery run
completed its artifact pipeline but averaged only 82.9/1,000 steps and failed the velocity/no-fall
gate. Two later non-tenant 200M no-push runs improved mean episode length to 760.25 on L40S and
763.45 on H100, yet both remained below the all-episode no-fall gate. That is useful learning
progress, not an accepted walking policy. A separate 100k custom-biped run was a Stand Balance task,
not Walk Forward, and recorded 100% fall rate; it is unrelated to the G1 card and is not a curation
candidate.

There are also three real-data mismatches in the just-landed showcase adapter. Runtime metrics use
canonical environment names (`Ant-v5`, `Go1JoystickFlatTerrain`, and so on) while the catalog uses
friendly IDs; evaluation success is the object `{"met": bool, "criterion": ...}` rather than a
bare boolean; and the serializer currently takes duration/configuration labels from current catalog
constants instead of the pinned run's resolved evidence. Tests built around synthetic manifests do
not expose those mismatches.

Constraints: public routes remain unauthenticated and read-only, the bucket remains private,
tenant-owned 32-character job identities remain forbidden pins, cloud work follows increasing-cost
gates, immutable image/config revisions are mandatory, and all temporary compute must be stopped or
deleted when its task ends. Implementation and any commits stay on `debug-portal` under the
temporary branch policy.

## Goals / Non-Goals

**Goals:**

- Publish six already-passing examples without rerunning their training.
- Make promotion reproducible and fail closed on identity, integrity, provenance, success, progress,
  measurement, and public-schema mismatches.
- Produce a G1 policy that visibly learns and passes the existing 20-episode, 1,000-step,
  velocity-at-least-0.4-m/s, no-fall gate, or stop at a predeclared budget with the card unpublished.
- Show evaluated initial/intermediate/selected progress with exact checkpoint steps and honest
  metrics, not merely “job completed.”
- Select L40S or H100 from passing cost-to-result evidence and leave no idle builder or accelerator.

**Non-Goals:**

- Restoring public gallery training or allowing visitors to rerun/parameterize examples.
- Publishing tenant jobs, copying private robot inputs, or relaxing the tenant/showcase resolver
  boundary.
- Treating artifact completion, reward increase, standing, short-horizon motion, or a single good
  seed as locomotion success.
- Lowering the G1 threshold, shortening its horizon, reducing evaluation breadth, or relabeling the
  rough-terrain task after seeing a failure.
- Improving the generic custom-robot 100k quick profile; that is a separate product change.

## Decisions

### Reuse six accepted source runs; do not pay for identical retraining

The curator first validates the six named source prefixes byte-for-byte with the current artifact
reader and independently checks their resolved config, immutable image revision, success object,
checkpoint identity, measured runtime/cost inputs, and visual progression. It emits a machine-
readable acceptance record containing only safe provenance and exact digests. `SHOWCASE_RUNS` is
then changed from placeholders to those accepted non-tenant IDs (or to deterministic promoted IDs
if derived progress evidence must be materialized without mutating the source prefix).

Alternative considered: submit seven new jobs for symmetry. Rejected because it spends CPU/GPU
budget while adding variance and no product evidence. The immutable source run is the evidence;
curation is verification, not a freshness contest.

### Add a typed curated-evidence adapter rather than special cases in the serializer

The artifact reader gains a showcase-evidence read that returns one typed internal record:
validated manifest, sanitized resolved configuration, sanitized runtime versions, normalized
evaluation outcome, measured benchmark/runtime, and progress checkpoints. Canonical runtime
environment identity is compared against a server-owned per-example expected value, not against the
friendly UI ID. Evaluation normalization accepts the documented runtime `success.met` shape and
rejects missing, non-boolean, contradictory, or legacy ambiguous values. The public serializer uses
this record for executed configuration, checkpoint, duration, cost, hardware, and revision; catalog
text remains presentation copy only.

The typed record is cached durably beside the manifest with its source run ID and evidence digest.
Cache reuse is allowed only while the hardcoded run ID and digest still match. Raw resolved config
is allowlisted field-by-field before caching/serialization, so a future runtime field is private by
default.

Alternative considered: translate `Ant-v5` to `ant` and `success.met` inline in `ShowcaseService`.
Rejected because it would fix two symptoms while leaving displayed configuration/cost detached from
the pinned evidence and would make future schema drift hard to reject coherently.

### Publication means artifact-complete and task-successful

A pinned run publishes only when all integrity/provenance checks pass and normalized
`evaluation.success` is true. A completed but below-threshold run is still retained for diagnosis,
but `GET /showcase` omits it and direct access returns the same 404 as any unpublished entry. The
curator prints a sanitized reason and never “promotes with warning.”

Alternative considered: publish failed examples with an honest red failure badge. Rejected for this
seven-card surface because its product promise is “verified examples”; failed diagnostics belong in
engineering evidence, not the public proof set.

### Progress is evaluated evidence with a selected checkpoint

For a curated run, initial, intermediate, and candidate checkpoints are associated with exact step,
digest, deterministic selection-set metrics, and rollout identity. Selection uses seeds distinct
from the final acceptance set and ranks locomotion checkpoints lexicographically by: number of
full-horizon no-fall episodes, minimum achieved forward velocity, mean episode length, then mean
velocity. Reward alone never selects G1. The selected checkpoint receives the unchanged final
20-episode acceptance evaluation. SB3 checkpoints use their configured mean-reward criterion.

The public progress payload reports step, normalized success measures, and media ID for the initial,
representative intermediate, and selected checkpoint. If a retained source run lacks structured
checkpoint metrics, a bounded evaluation-only curation job may generate them under a deterministic
new public run prefix; it must not modify the accepted source prefix. A progression stage that is
worse than the previous stage remains visible and labeled as regression rather than being silently
substituted.

Alternative considered: label the nearest 25% checkpoint “mid” and the final checkpoint “best.”
Rejected because the existing G1 evidence demonstrates that later training can still terminate
early; step count is not model quality.

### G1 uses a stop/go evidence ladder, not an unconditional longer run

The ladder is sequential and each phase must pass before the next spends money:

1. **Retained-checkpoint sweep** — on L40S, screen all retained checkpoints from the two 200M
   no-push runs with a small deterministic selection set, then run the full 20-episode acceptance
   set on at most the top three. If one passes, promote it and stop; no training occurs.
2. **Flat-gait prerequisite** — if no checkpoint passes, freeze an immutable candidate derived from
   the pinned upstream G1 PPO contract and train a 100M `G1JoystickFlatTerrain` no-push stage from
   scratch. Continue only if the selected checkpoint sustains commanded walking on the full
   horizon; standing or reward-only improvement stops the candidate.
3. **Rough-terrain fine-tune** — resume the validated flat checkpoint into the no-push rough-terrain
   task for up to 200M additional steps. Preserve 8,192 environments, privileged critic, 1,000-step
   episodes, and 20 evaluation points; freeze any stability/reward/curriculum changes in source and
   CI before launch. Selection checkpoints use the separate selection seeds and stop early if two
   consecutive gates regress without a recovery checkpoint.
4. **Fresh acceptance run** — after the contract is frozen, produce one clean curated run whose
   resolved provenance records both curriculum phases and parent checkpoint digest. It must pass
   the unchanged final gate and complete all checksummed media/bundle artifacts before pinning.

This makes “train longer” conditional: the likely budget is 100M flat plus at most 200M rough, not a
blind repeat of the failed 25M or 200M setup. Exact reward-scale or command-curriculum changes are
not guessed in this proposal; the implementation task first inspects the pinned Playground v0.2.0
G1 contract and allowlists one reviewed candidate at a time. Candidate count, GPU-hours, and dollar
ceiling are written into the operator record before launch. Exceeding any ceiling leaves G1
unpublished and requires a new reviewed change.

Alternative considered: continue the final failed checkpoint directly to 400M with identical
settings. Rejected as the default because both accelerators converged to the same early-termination
failure; more steps alone do not address gait acquisition versus rough-terrain robustness and can
hide checkpoint regression.

### L40S first, H100 only for a declared wall-time reason

Evaluation sweeps and G1 pilots use L40S because the measured 200M no-push run cost about $4.23
versus $5.89 on H100, although H100 was about 1.8 times faster. If the frozen L40S candidate passes
within the declared timeout, it is the production hardware and no H100 duplicate is launched. H100
is tried only when the identical frozen workload exceeds a declared L40S wall-time/operational
deadline or fails a measured capacity gate; a policy-quality failure on L40S is not treated as a
hardware failure unless the exact H100 run passes.

### Partial publication is the deployment unit

The six accepted pins can ship while G1 remains a placeholder. The catalog order remains stable and
the evidence gate naturally returns six cards. G1 is added in a later commit only after acceptance;
there is no all-or-nothing release and no pressure to weaken its gate for visual completeness.

## Risks / Trade-offs

- **[Historical source artifact no longer satisfies current validation]** -> Leave only that card
  unpublished, run evaluation/finalization from its retained checkpoint into a new curated prefix,
  and never patch the historical prefix in place.
- **[Real schema normalization accidentally broadens public data]** -> Parse into an allowlisted
  typed record, add fixtures from sanitized real manifests, and assert secrets/storage/tenant fields
  cannot serialize.
- **[Checkpoint selection overfits acceptance seeds]** -> Use disjoint deterministic selection and
  final seed sets; run the unchanged final set only on the bounded shortlist.
- **[Flat-to-rough transfer forgets the gait]** -> Keep exact milestone evaluations, select the best
  stable checkpoint rather than the last one, and stop after two consecutive regressions.
- **[G1 never passes within budget]** -> Preserve all diagnostic evidence, clean up compute, keep the
  placeholder/unpublished state, and require a separate proposal for a new task/reward design.
- **[Provider history conflicts with compute cleanup]** -> Stop/delete chargeable VM instances and
  follow the current explicit retention instruction for Serverless AI job history; record the exact
  cleanup state without deleting SaaS rows or durable S3 evidence.
- **[Pinned prices become stale]** -> Display rate date with measured runtime/cost, and recurate via a
  reviewed source change rather than silently recomputing old evidence at request time.

## Migration Plan

1. Add real-manifest fixtures and the typed evidence adapter while all pins remain placeholders.
2. Run the local/backend/frontend/OpenSpec gates and an offline audit of the six source runs.
3. Materialize new curated prefixes only for sources that need derived progress evidence; otherwise
   leave the verified source prefixes untouched.
4. Replace six placeholders, deploy through the normal `debug-portal` CI/GitOps path, and verify the
   anonymous catalog/detail/artifact surface at desktop/mobile with no training control.
5. Execute the G1 ladder under explicit operator budget and cleanup gates; pin G1 in a separate
   reviewed commit only after its full acceptance record passes.
6. Audit active jobs, instances, disks, IPs, temporary rules, and the reusable builder after every
   cloud phase; stop/delete chargeable instances immediately.

Rollback is a source revert from a real pin to its placeholder. The next request omits the card;
the private artifacts remain durable and no database or bucket rollback is needed. If the evidence
cache schema changes, its rows are disposable and rebuilt from the hardcoded pinned prefix.

## Open Questions

- What exact stability/curriculum fields exist in the pinned Playground v0.2.0 G1 config and can be
  narrowly allowlisted without forking upstream environment code? Resolve before the first pilot.
- Are all initial/intermediate checkpoints for the six historical passing sources still durable,
  or do any require a derived curation prefix to supply structured progress evidence?
- What candidate-count, L40S/H100-hour, and dollar ceilings does the operator approve for G1? Record
  them before any paid run; the task defaults to stopping rather than inferring authorization.
