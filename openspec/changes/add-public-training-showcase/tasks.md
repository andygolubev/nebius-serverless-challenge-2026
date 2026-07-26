## 1. Pinned showcase run identity

- [x] 1.1 Add `SHOWCASE_RUNS: dict[str, str]` to `saas/backend/app/catalog.py` mapping each of the seven gallery example IDs to its curated S3 run ID, using clearly-marked placeholder-shaped values that will fail the publication gate until the curated runs land
- [x] 1.2 Add a startup validator that checks each pinned run identity against the safe run-identity pattern, confirms in-prefix containment under `sim2policy/`, and rejects duplicates and any value colliding with the tenant job identity space; an invalid entry is logged and left unpublished rather than failing startup
- [x] 1.3 Repurpose `GallerySettings` in `saas/backend/app/settings.py` as a showcase publication switch (drop the immutable-training-image requirements, which no longer gate anything submittable) and update the `/health` field it reports
- [x] 1.4 Add a `resolve_showcase_run(example_id) -> str | None` resolver whose only input is an example ID and only output is a literal from `SHOWCASE_RUNS`, with no parameter accepting a run ID, job ID, key, or prefix

## 2. Showcase read path and publication gate

- [x] 2.1 Add a showcase manifest read in `saas/backend/app/artifacts.py` that calls `read_manifest(pinned_run_id, pinned_run_id)` and reuses the existing safe-path, in-prefix, required-artifact, and digest validation
- [x] 2.2 Implement the publication gate: an entry publishes only when its manifest is readable and valid, its required artifact set is present with safe identifiers/names/kinds/content types/integrity metadata, and its recorded evaluation state exists; any failure yields an unpublished entry with a sanitized log
- [x] 2.3 Cache validated showcase manifests durably in the existing `artifacts` table keyed by pinned run ID via `store.py`, and add a short-TTL negative cache so a permanently-absent run does not re-hit S3 per request
- [x] 2.4 Add a showcase serializer producing display metadata (label, task, description, avatar, expected result, backend/hardware labels, resolved configuration the run executed, observed duration/cost, success criterion, primary metric, acceptance revision) with no tenant email, job ID, bucket name, object key, credential, or presigned URL
- [x] 2.5 Define the publicly exposed artifact-kind allowlist as a single constant covering media, metrics, report, resolved config, runtime versions, checkpoint, and policy bundle

## 3. Public API routes

- [x] 3.1 Add `GET /showcase` in `saas/backend/app/main.py` with no session dependency, returning published entries in documented gallery order and 200-with-empty-list when none validate
- [x] 3.2 Add `GET /showcase/{example_id}` returning identity, resolved configuration, structured metrics, evaluation state separate from infrastructure completion, checkpoint identity, runtime versions, measured runtime/cost, and the public artifact list; 404 for unknown, hidden, or gate-failing entries without distinguishing the cases
- [x] 3.3 Add `GET /showcase/{example_id}/artifacts/{artifact_id}` resolving the opaque identifier against the cached validated manifest and redirecting to a short-lived presigned URL with range support, correct content type, and safe filename; 404 for any identifier absent from the manifest
- [x] 3.4 Confirm the showcase handlers take no session parameter at all (not an optional one), so a request carrying a valid bearer token receives a byte-identical response
- [x] 3.5 Add per-client-IP rate limiting to the public showcase routes, reusing the bounded-attempt pattern in `auth.py`, returning 429 without affecting other clients
- [x] 3.6 Ensure storage and upstream failures on public routes degrade to sanitized unavailable responses that leak no bucket, key, or credential detail, never an unhandled 5xx
- [x] 3.7 Reshape `GET /training-options` into unauthenticated showcase display metadata that advertises no submittable environment, algorithm, preset, profile, or parameter contract, and returns only published entries

## 4. Public frontend surface

- [x] 4.1 Add session-free showcase calls to `saas/frontend/src/api.ts` that omit the `Authorization` header entirely and never dispatch `SESSION_EXPIRED_EVENT`
- [x] 4.2 Invert routing in `saas/frontend/src/App.tsx` so the root renders the showcase regardless of session state, `Login` becomes an explicitly-reached destination with no flash of a login screen, and a 401 in the authenticated app clears the session and returns to the showcase
- [x] 4.3 Build the `Showcase` view: responsive published-example cards with avatar, task story, expected result, backend/hardware badges, executed configuration, and measured duration/cost, plus a designed empty state for zero published entries
- [x] 4.4 Build the `ShowcaseDetail` view reusing `resultView.ts`, the existing video player, and the metrics/expandable-details rendering, so a showcase run and a custom job result read as the same product
- [x] 4.5 Wire anonymous media playback through public showcase artifact URLs: primary final rollout, label-selectable progression/intermediate videos, seeking without full download, and a human-readable unavailable state with retry
- [x] 4.6 Add the sign-in call to action that leads to login and then to the My Robots workspace, and verify no start/run/re-run/retrain/queue control exists anywhere in the showcase for signed-in or anonymous users
- [x] 4.7 Add the public bundle download action with the simulator-only disclosure shown before download, omitted entirely when the entry's bundle is unpublished or failed validation
- [x] 4.8 Verify the showcase and detail at 375px width, keyboard-only input, and both `prefers-color-scheme` values using the existing token set with no new styling primitives

## 5. Remove the gallery training path

- [ ] 5.1 Delete `catalog.resolve_gallery` and `catalog.expand_preset`, and reshape `catalog.serialize` for showcase display; retain `JOB_SPECS` as the record of what each curated run executed
- [ ] 5.2 Remove the gallery, preset, and raw environment/algorithm branches of `main.py::submit_job` so `POST /jobs` accepts no `gallery_example_id`, `gallery_profile_id`, `preset`, `environment`, `algorithm`, or parameter override, and refuses every such payload while naming the supported custom-training path
- [ ] 5.3 Narrow the Nebius backend in `saas/backend/app/orchestration.py` to its typed custom preparation and custom training submission sources only, removing the public-catalog production submission source and its validator
- [x] 5.4 Delete `saas/frontend/src/views/Composer.tsx` and its "New Job" navigation entry
- [x] 5.5 Retarget the My Robots handoff from "Train a verified example" to "See a verified example" pointing at the read-only showcase, keeping the preparation path as the only training action
- [x] 5.6 Update the dashboard empty state to guide tenants to My Robots for upload/setup/preparation, offering the showcase as an example of a finished run
- [ ] 5.7 Verify historical gallery jobs still render their persisted example identity, label, avatar, metrics, and artifacts in the dashboard and detail views, with no broken re-run affordance

## 6. Tests

- [ ] 6.1 Rewrite `saas/backend/tests/test_gallery.py` around the public showcase: anonymous catalog and detail reads, documented ordering, no tenant/storage identity in responses, identical response with and without a bearer token, 200-with-empty-list when nothing validates, and 404 for unknown or gate-failing entries
- [ ] 6.2 Rewrite `saas/backend/tests/test_gallery_artifacts.py` for public artifact delivery: range support and `video/mp4` on media, safe filename on download, 404 for identifiers absent from the manifest, bounded read-only single-object presigned URLs, and withheld entries on out-of-prefix, missing, or digest-mismatched manifest members
- [ ] 6.3 Add the negative test that no showcase route creates or mutates a job, preparation, remote resource, or storage object under any method, parameter, or header
- [ ] 6.4 Add the negative test that substituting a tenant job ID, tenant run ID, or traversing value into any showcase route returns 404 and performs zero reads against a tenant prefix, and that a showcase example ID passed to a tenant artifact route returns 404
- [ ] 6.5 Add tests that `POST /jobs` refuses every gallery example ID, gallery profile ID, and Go1 preset ID without creating a SaaS record or Nebius resource, and that the only job-creating endpoint is `POST /robot-setups/{setup_id}/training-jobs`
- [ ] 6.6 Add a test that a showcase manifest lookup cannot return a tenant job's manifest and vice versa, given the shared `artifacts` cache table
- [ ] 6.7 Add a test that the orchestration layer exposes no public-catalog submission validator and that no showcase call path reaches a launch/submit function
- [x] 6.8 Replace composer coverage in `saas/frontend/src/views/gpu-demo.test.tsx` with unauthenticated showcase coverage: root renders the showcase with no session, empty state, detail navigation, media selection, absence of any training control, and the sign-in call to action
- [ ] 6.9 Add a rate-limit test asserting 429 for a single abusive client while the showcase stays available to others

## 7. Deploy and verification

- [ ] 7.1 Confirm the three public routes are reachable through the existing ingress without a session header and that static frontend serving still wins for non-API paths
- [ ] 7.2 Confirm no new secret, volume, bucket ACL, public prefix, or credential change is required, and that the artifact bucket remains private
- [ ] 7.3 Run the backend and frontend test suites and record results in `IMPLEMENTATION_LOG.MD`
- [ ] 7.4 Verify in the deployed UI that an anonymous browser session reaches the showcase, sees the correct empty or published state, plays any published media, and finds no training control; then verify a signed-in tenant can still prepare and start their own custom robot
- [ ] 7.5 Run `openspec validate add-public-training-showcase --strict` and confirm the change is ready to archive
