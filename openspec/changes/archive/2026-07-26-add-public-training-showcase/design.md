## Context

The current SaaS control plane (`saas/backend/app/`) treats the seven verified examples as a
submission catalog. `catalog.py` holds `GALLERY_EXAMPLES` (display metadata) joined to `JOB_SPECS`
(keyed by `(environment, algorithm)` → immutable image, config, platform, preset, timeout, timesteps,
cost, acceptance date). `main.py::submit_job` branches three ways — gallery example, Go1 preset, or
raw environment/algorithm — resolves through `catalog.resolve_gallery` / `expand_preset` /
`resolve_config`, persists a `Job`, and calls `_backend.launch`. Everything except `/health`,
`/auth/*`, and `/robot-samples` requires `require_session`.

Artifact access already has the shape the showcase needs. `artifacts.py::read_manifest(job_id,
run_id)` takes the two identities separately, so a showcase read is `read_manifest(pinned_run_id,
pinned_run_id)`. Validation (`_SAFE_REL`, `_SHA256`, in-prefix containment, required-artifact sets,
bundle digest/member checks) is already run-scoped rather than tenant-scoped, and `presigned_url` is
already the delivery mechanism. `store.py`'s `artifacts` table is keyed on a single `job_id` text
column that functions as a generic cache key.

The frontend (`saas/frontend/src/`) has no unauthenticated view at all: `App.tsx` renders `Login`
whenever `session.token === null`, and `api.ts` attaches the bearer header to every call. The
showcase is the first public surface, so routing and the API client both need a session-free path.

Constraints: the artifact bucket must stay private; the pinned runs do not exist yet (a separate
change performs them), so every stage must behave correctly with zero published entries; and existing
gallery jobs in tenants' dashboards must keep rendering.

## Goals / Non-Goals

**Goals:**
- One public, read-only surface (`GET /showcase`, `/showcase/{id}`,
  `/showcase/{id}/artifacts/{artifact_id}`) that anonymous visitors can browse and play video from.
- Curated run identity pinned in reviewable server source, unreachable and uninfluenceable by clients.
- Structural impossibility — not merely absence — of starting training from a showcase route, and of a
  showcase route resolving a tenant-owned run.
- Exactly one job-creating endpoint left in the service.
- Correct, non-error behaviour while the showcase is entirely empty.

**Non-Goals:**
- Performing the curated gallery training runs. Separate change; this one only pins the IDs and reads
  whatever validates.
- A CDN, edge cache, or public bucket policy. Presigned redirects from the pod are sufficient at this
  traffic level.
- Any admin UI or API for choosing showcase entries. Pinning is a code change and a deploy.
- Re-running, forking, or parameterizing a showcase example — now or as a hidden capability.
- Changing the custom-robot upload, environment builder, preparation, or training flow.

## Decisions

### Two independent identity resolvers rather than one parameterized artifact path

The tenant path resolves `(tenant_email, job_id) → Job → run_id` through `_store.get`. The showcase
path resolves `example_id → SHOWCASE_RUNS[example_id] → pinned_run_id` through a frozen dict in source.
These are separate functions that share only the low-level `ArtifactReader`.

*Why not one resolver with an `authenticated: bool`?* Because a boolean is exactly the kind of
parameter that gets defaulted wrong once. With two resolvers, "a showcase route cannot reach a tenant
run" is true by construction: the showcase resolver's only input is an example ID, and its only output
is a run ID from a literal in source. There is no code path from an HTTP parameter to a tenant run ID.
The negative test asserts this by passing tenant job IDs into every showcase route and expecting 404
with zero calls against the tenant prefix.

*Cost:* mild duplication of the "resolve artifact ID in manifest → presign → redirect" tail. That tail
is ~15 lines and duplicating it is cheaper than a shared function whose safety depends on a flag.

### Pinned runs as a frozen module-level map validated at startup

```python
SHOWCASE_RUNS: dict[str, str] = {"go1-walker": "<run-id>", ...}   # example ID -> S3 run ID
```

Validated at startup against the existing safe run-identity pattern; an unsafe or malformed value
means that entry is never published (logged, not fatal — one bad literal should not take the service
down when the other six are fine). A value that duplicates another entry's, or collides with the tenant
job identity space, is likewise refused.

*Alternatives considered:* env var / mounted JSON gives ops flexibility but moves the most
security-relevant allowlist in the service out of code review, and there is no operational need to swap
curated runs without a deploy. DB-seeded entries would need a new admin auth surface — a new
attack surface to solve a problem we do not have.

### Publication gate = manifest validity, computed lazily and cached durably

An entry publishes only if `read_manifest` returns a manifest that passes existing validation and
contains the required artifact set. Results are cached in the existing `artifacts` table keyed by the
pinned run ID, so anonymous traffic is served from SQLite rather than crawling S3 per request. A pinned
run whose manifest is absent (the expected state until the curated runs land) yields an unpublished
entry — a normal 200-with-fewer-cards, never a 5xx.

*Why lazy and not startup-only?* The curated runs land after this change deploys. A startup-only gate
would require a pod restart to pick up each new run; lazy-with-cache picks it up on the next request.
A negative cache with a short TTL keeps a permanently-missing run from hammering S3.

*Why reuse the `artifacts` table?* Its `job_id` column is already a plain text cache key with no FK to
`jobs`, so no migration is needed. Pinned run IDs are validated distinct from job IDs, so the two
never collide in that keyspace.

### Deletion, not disablement, of the gallery submission path

`catalog.resolve_gallery`, `catalog.expand_preset`, and the gallery/preset branches of `submit_job` are
removed rather than gated behind `_gallery_settings.enabled`. `POST /jobs` loses its gallery and preset
inputs entirely; the endpoint either disappears or narrows to a 410-with-explanation for any payload.

*Why delete?* A feature-flagged submission path is still a path — one that a stale env var, a test
fixture, or a future refactor can re-enable, contradicting a spec that promises visitors nothing can be
triggered. `GallerySettings` survives as a showcase publication switch, not a training switch.

The `JOB_SPECS` table stays: it is the record of what each curated run executed, which is exactly the
metadata the showcase displays. It just no longer feeds a submission builder.

### `GET /training-options` reshaped rather than removed

It becomes display metadata for the showcase and stops advertising submittable environments,
algorithms, presets, and profiles. Keeping the path avoids a hard break for anything already fetching
it, while the reshaped body makes the loss of submittability self-evident. `GET /showcase` is the
name new code should use; `/training-options` returning the same published-entry list is acceptable.

### Public routes bypass `require_session` explicitly, and ignore tokens when present

Showcase handlers take no `session` dependency at all — not an optional one. A route with an optional
session is a route where someone can later write `if session: ...` and widen access. Access is decided
solely by the pinned-run allowlist, so a request bearing a valid token gets a byte-identical response.

Rate limiting is applied per client IP on the public routes, reusing the bounded-attempt pattern
already in `auth.py` rather than introducing a dependency.

### Frontend: showcase is the root view, login is a destination

`App.tsx` inverts: unauthenticated no longer implies `Login`. The root route renders `Showcase`
regardless of session state; `Login` is reached by an explicit action; a 401 in the authenticated app
clears the session and returns to `Showcase`. `api.ts` gains showcase calls that omit the
`Authorization` header entirely and never dispatch `SESSION_EXPIRED_EVENT` — a public 404 is not a
session problem.

`resultView.ts`, the player, and the metrics/details rendering are reused for the showcase detail so a
showcase run and a custom job result look like the same product. `Composer.tsx` is deleted; the "New
Job" nav entry goes with it.

### Public bundle download included, one allowlist away from reversible

Per the proposal's stated assumption, the policy bundle is publicly downloadable for published entries.
The publicly exposed artifact kinds are one allowlist constant in the showcase serializer, so restricting
anonymous access to media plus metrics later is a single-line change plus a test flip, not a redesign.

## Risks / Trade-offs

- **Anonymous bandwidth and presign abuse** → Presigned URLs are short-lived, read-only, and scoped to a
  single validated object; showcase routes are IP-rate-limited; the exposed artifact set is a small
  fixed allowlist. Worst case is repeated download of seven known public demo runs, which is what a
  showcase is for.
- **Removing `POST /jobs` gallery submission is breaking for any external caller** → Accepted and
  intended: the whole point is that visitors cannot spend GPU budget. Historical jobs stay readable, and
  the rejection response names the supported custom-training path.
- **The showcase ships empty** → Specified as correct behaviour with a designed empty state, and
  covered by a test asserting `GET /showcase` returns 200 with an empty list when no run validates. The
  change is deployable and honest before the curated runs exist.
- **Duplicated presign/redirect tail in two resolvers could drift** → Both paths are covered by tests
  asserting range support, content type, safe filename, and 404-on-unknown-identifier, so drift in
  either surfaces immediately.
- **Reusing the `artifacts` table for showcase caching couples two concerns in one table** → Mitigated
  by validating that pinned run IDs are distinct from the job identity space, plus a test that a
  showcase lookup cannot return a tenant manifest and vice versa. The alternative — a second table —
  costs a migration for no safety gain given that check.
- **A pinned run could be swapped in S3 under a stable ID, changing what the public sees without a code
  change** → The manifest's digests are validated on read and the entry is withheld on mismatch;
  showcase revisions are pinned per release, so a content swap under a pinned ID fails validation rather
  than silently republishing.
- **`prefers-color-scheme`, 375px, and keyboard operability now apply to a public marketing-facing
  surface** → The showcase reuses the existing token set and layout primitives rather than introducing
  new styling, and its accessibility scenarios are explicit spec requirements with tests.

## Migration Plan

1. **Backend read path first, additive.** Add `SHOWCASE_RUNS` (initially with the intended run IDs,
   which will not yet resolve), the showcase resolver, publication gate, caching, and the three public
   routes. Ship this alone: `GET /showcase` returns `200` with an empty list, nothing else changes, and
   the gallery still works. Deployable and safe on its own.
2. **Frontend public surface.** Invert `App.tsx` routing, add `Showcase` and `ShowcaseDetail`, wire the
   session-free API calls, add the sign-in call to action. At this point a visitor sees the empty-state
   showcase.
3. **Remove the training path.** Delete the gallery/preset branches of `submit_job`, `resolve_gallery`,
   `expand_preset`, and `Composer.tsx`; drop the "New Job" nav entry; retarget the My Robots handoff at
   the showcase; narrow the Nebius backend to its custom typed sources. This is the breaking step and
   lands as one commit so the API and UI never disagree about whether gallery training exists.
4. **Rewrite the affected tests** alongside each step, including the negative tests (no showcase route
   creates a job; no showcase route resolves a tenant run; `POST /jobs` refuses every gallery and preset
   payload).
5. **Curated runs land separately.** As each pinned run publishes a valid manifest, its card appears on
   the next request with no deploy.

**Rollback:** steps 1–2 are additive and roll back by reverting. Step 3 is the irreversible-in-spirit
step; rolling it back restores gallery training but leaves showcase reads working, since they share no
code. No data migration means no data rollback.

## Open Questions

- The actual pinned run IDs are unknown until the curated-runs change performs them. Implementation
  should land `SHOWCASE_RUNS` with clearly-marked placeholder-shaped values that fail the publication
  gate rather than inventing plausible IDs.
- Whether `GET /training-options` should eventually be dropped in favour of `GET /showcase` alone. Kept
  reshaped here; removal is a separate cleanup once no client reads it.
- Cost and duration labels for entries whose curated run used a different workload than the historical
  Go1 profiles: the spec requires the display to match what the pinned run actually recorded, so any
  disagreement withholds the card until the declaration is corrected.
