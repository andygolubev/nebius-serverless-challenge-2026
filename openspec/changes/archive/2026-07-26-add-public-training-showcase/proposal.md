## Why

Today the seven verified examples are a *trainable* catalog behind email login: a visitor must
authenticate before they can see anything, and every card is a button that spends GPU money. That
inverts the product story — the examples exist to *prove* sim2policy works, and proof is worth
nothing if nobody can look at it. Meanwhile the only training we actually want tenants to spend
compute on is their own uploaded robot, which is already gated by upload, environment builder, and
preparation.

Turning the gallery into a public, read-only showcase of runs we have already paid for makes the
evidence visible to every visitor at zero marginal cost, and leaves exactly one way to start a
training job: an authenticated owner training their own custom robot.

## What Changes

- **New public showcase**: an unauthenticated page listing the seven examples, each backed by one
  server-pinned, already-completed training run. A visitor can read the task story, expected result,
  measured duration/cost, evaluation metrics, and play the rollout videos without an account.
- **Pinned run identity**: each showcase entry hard-binds a gallery example ID to one curated S3
  run ID in backend source (`SHOWCASE_RUNS` in `catalog.py`), reviewable in git and immutable per
  release. Producing those runs is out of scope here (separate change); an entry whose pinned run is
  absent or incomplete is simply omitted from the public response.
- **Public artifact delivery**: a session-free artifact route resolves an allowlisted artifact ID
  against the pinned run's validated manifest and redirects to a short-lived presigned URL. Callers
  never supply keys; the bucket stays private; no showcase route can reach a tenant run.
- **BREAKING — gallery training is removed**: `POST /jobs` no longer accepts `gallery_example_id`
  or a Go1 `preset`; the seven-card "New Job" composer is deleted from the web app.
  `GET /training-options` stops being a submission catalog and becomes display metadata for the
  showcase. The only job-creating endpoint left is
  `POST /robot-setups/{setup_id}/training-jobs`.
- **BREAKING — public catalog orchestration is removed**: the Nebius backend keeps only its typed
  custom preparation/training submission sources. The MJX public-catalog submission path is gone.
- Existing gallery Jobs created before this change stay readable in an owner's dashboard with their
  persisted example identity, label, and avatar. Nothing is deleted.
- Authenticated navigation loses "New Job" and gains a route into the same showcase, so the
  "Train a verified example" handoff in My Robots becomes "See a verified example" and the only
  training call to action is Prepare/Start on the tenant's own setup.

**Assumption stated for review**: the showcase exposes the policy bundle download to anonymous
visitors alongside the videos, on the grounds that the bundle *is* the artifact being showcased. If
that bandwidth or reuse exposure is unwanted, restricting anonymous access to media plus metrics is
a one-line allowlist change in the showcase artifact contract.

## Capabilities

### New Capabilities
- `public-training-showcase`: the unauthenticated showcase contract — server-pinned curated run per
  gallery example, completeness/staleness gating before publication, public catalog and per-example
  result payloads, session-free allowlisted artifact access, and the invariant that no showcase
  route can create a job or reach a tenant-owned run.

### Modified Capabilities
- `trainable-examples-gallery`: the seven examples become display-and-showcase identities rather
  than trainable entries. "Server-resolved gallery submission" is removed; executability gating is
  replaced by showcase-evidence gating; "Bring Your Robot remains isolated" inverts — custom
  training is now the *only* training path.
- `saas-job-customization`: `POST /jobs` no longer accepts gallery example IDs or Go1 profile IDs;
  `GET /training-options` is redefined as showcase display metadata, not a submission catalog. The
  backward-compatible Go1 preset submission requirement is removed.
- `saas-nebius-orchestration`: the public-catalog production job specification is dropped as a
  submission source; only owned custom preparation and `custom-ppo-quick` typed sources remain.
- `saas-web-ui`: adds the unauthenticated showcase route (landing view, example detail, player) and
  a sign-in call to action; removes the seven-card job composer; retargets the My Robots handoff at
  the showcase; keeps gallery identity rendering for historical jobs.
- `saas-artifact-access`: adds public showcase artifact reads and delivery scoped to pinned run
  prefixes, distinct from and unable to cross into the tenant-authorized boundary.
- `policy-bundle-export`: bundle-gated completion no longer applies to new gallery jobs (none can
  be created); bundle exposure gains the public showcase delivery path beside the tenant one.

## Impact

- **API**: removes the gallery/preset branches of `POST /jobs` and the composer contract in
  `GET /training-options`; adds `GET /showcase`, `GET /showcase/{example_id}`, and
  `GET /showcase/{example_id}/artifacts/{artifact_id}`, all unauthenticated.
- **Backend** (`saas/backend/app/`): `catalog.py` (pinned `SHOWCASE_RUNS`, `resolve_gallery` and
  `expand_preset` removal, `serialize` reshaped), `main.py` (new public routes, `POST /jobs`
  narrowed or removed), `artifacts.py` (showcase manifest read/validate, reuse of
  `read_manifest(run_id, run_id)` and `presigned_url`), `store.py` (manifest cache keyed by pinned
  run ID — the existing `artifacts.job_id` column already serves as a generic cache key, no
  migration), `settings.py` (`GallerySettings` becomes a showcase switch).
- **Frontend** (`saas/frontend/src/`): `App.tsx` gains an unauthenticated route so the showcase
  renders before login; new `Showcase`/`ShowcaseDetail` views reusing `resultView.ts` and the
  existing player; `Composer.tsx` deleted; `api.ts` gains session-free showcase calls;
  `MyRobots.tsx` handoff copy and target updated.
- **Tests**: `test_gallery.py` and `test_gallery_artifacts.py` are rewritten around showcase reads
  and the absence of gallery submission; `gpu-demo.test.tsx` composer coverage is replaced by
  unauthenticated showcase coverage; a negative test asserts no showcase route accepts a tenant run
  ID or creates a job.
- **Deploy**: no new secret or volume. The public routes must be reachable without the session
  header through the existing ingress; static frontend serving is unchanged.
- **Out of scope**: performing the curated gallery training runs that the pinned IDs point at. Until
  that lands, the showcase publishes only entries whose pinned run already validates — an empty or
  partial showcase is a correct intermediate state.
