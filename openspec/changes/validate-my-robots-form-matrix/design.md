## Context

The My Robots page spans four boundaries: React form behavior, FastAPI validation and persistence, asynchronous preparation/training state, and the deployed browser/API path. Existing tests cover representative uploads, compatibility rules, scenes, object rejection, and several lifecycle states, but their fixtures are hand-written and no single run proves that every current catalog value appears in a scenario. The live form also hides the environment builder until an upload succeeds, so a shallow page smoke misses most controls.

The current server-owned catalog has two declared robot types; five compatible robot-type/task pairs; four scenes; four optional object types; seven bounded parameters per object; a six-total-object limit; and eight V1 preparation-eligible robot/task/scene combinations. Exhaustively multiplying every possible object list and continuous numeric value is neither finite nor useful. The suite therefore needs exhaustive coverage of discrete choices and contract boundaries, with pairwise selection only at the slow browser layer.

Constraints include tenant ownership, 20 active models and 50 active setups per tenant, secret bearer sessions, soft deletion, asynchronous remote jobs, and the requirement to stop/delete cloud compute after use. Generated run evidence is local and gitignored. The existing public API remains the system under test; no test-only production endpoint or authentication bypass is introduced.

## Goals / Non-Goals

**Goals:**

- Prove that every visible My Robots control and every server-advertised discrete choice has an executable scenario.
- Exhaustively validate compatible and incompatible robot/task edges, all scenes, all object types, parameter boundaries, object capacity, persistence, ownership, and readiness projection in cheap tests.
- Exercise the same workflow through a real browser with a compact pairwise matrix and one end-to-end happy path per important state transition.
- Run independent cheap cases in parallel, aggregate all failures, and leave deterministic evidence that makes each failure directly reproducible.
- Separate no-cost validation from remote preparation and training so a skipped cost gate is reported honestly instead of being treated as passed.
- Make defect repair regression-first and require the relevant shard plus the full cheap gate to pass afterward.

**Non-Goals:**

- Infer morphology from the declared biped/quadruped radio choice; the current contract treats robot type as validated tenant metadata.
- Exhaust every ordering or repetition of up to six optional objects, or every real number inside a parameter range.
- Change the task, scene, object, preparation, or fixed training catalogs.
- Add a production test backdoor, expose credentials in reports, or make paid training part of ordinary CI.
- Use this form suite as proof of policy convergence; remote preparation proves compatibility and training completion reports measured outcomes separately.

## Decisions

### 1. Generate one canonical case inventory from server-owned contracts

Backend parametrization will read the real serialized environment catalog and canonical sample metadata, then emit stable case identifiers. The baseline inventory includes:

- both canonical sample uploads through both radio-control paths, while asserting the contract-defined outcome rather than attempting morphology inference;
- all 5 compatible robot/task pairs across all 4 scenes (20 no-optional-object setup cases);
- each of the 4 optional object types at defaults for every base setup (80 one-object cases), with readiness reasons derived from the real eligibility contract;
- each object parameter at default, minimum, maximum, just below minimum, just above maximum, empty/non-numeric browser state, and non-finite API input where representable;
- exact capacity and one-over-capacity cases for all four scene preset sizes; and
- all 8 V1-eligible combinations plus representative cases for every stable ineligibility reason.

The frontend uses the same catalog-shaped fixture and asserts that every catalog identifier appears in its coverage manifest. A catalog addition therefore fails with an uncovered-value diagnostic instead of silently reducing coverage. Stable identifiers, not display text alone, tie backend, component, browser, and report rows together.

Alternative considered: maintain a hand-authored spreadsheet of combinations. It is easier to read initially but drifts whenever the server catalog changes and cannot act as an executable completeness gate.

### 2. Use a validation pyramid rather than a full browser cross-product

Four layers balance speed and confidence:

1. FastAPI/Python contract tests exhaust the discrete matrix, validation bounds, ownership, idempotency, and readiness projection.
2. Vitest/Testing Library tests exhaust rendered choices, client-side disabling/error behavior, payload construction, saved-state rendering, and lifecycle actions with controlled API responses.
3. Playwright tests run against a local full-stack server with temporary SQLite and mock orchestration. They cover upload-to-save flows, downloads, deletion confirmation, reload persistence, keyboard/mobile operation, preparation states, retry, start idempotency, and error presentation using a catalog-driven pairwise set.
4. An opt-in deployed smoke suite runs against `https://sim-policy-trainer-challenge.info/` (or an explicit base URL) using an existing test-tenant session. It verifies deployed catalog/UI agreement and safe persisted workflows; remote preparation and training are separate flags and never implied by the default result.

Playwright is added as a development-only test dependency because it provides deterministic browser workers, downloads, responsive contexts, and CI artifacts. The in-app browser remains useful for exploratory diagnosis but is not the reproducible automation contract.

Alternative considered: run all 100+ positive setup cases through the browser. This adds substantial runtime and flakiness while duplicating API coverage; pairwise browser coverage catches wiring problems with a fraction of the cases.

### 3. Parallelize only isolation-safe work

The backend and component matrices are divided by stable `case_id` hash across CI shards. Local Playwright workers each receive a unique temporary database, mock-auth tenant, and artifact directory. Deployed mutation cases use a run prefix and unique object names; they run in parallel only when each worker has an independent test tenant, otherwise mutations are serialized while read-only browser assertions may remain parallel. Remote preparation/training is bounded separately and is never fanned out implicitly.

Each case has a timeout and teardown. Cleanup is targeted by the exact IDs created during the run, never by broad name matching. A cleanup failure fails the run and is visible in the report. If remote work is explicitly enabled, provider-job and instance audits are mandatory before the run can report clean.

Alternative considered: maximize workers against one production tenant. The model/setup quotas and soft-delete semantics make this fast but race-prone and capable of obscuring real failures.

### 4. Treat browser control inventory as a coverage contract

The suite maintains an explicit mapping for sample download, name, robot-type radios, file input, validation submit/errors, model download/delete/build actions, builder close/name/task/scene/object type, add/remove, every numeric parameter editor, review/save/errors, setup persistence/delete, Prepare, Retry, Start training, and the verified-example handoff. Tests fail when a mapped control is missing, duplicated unexpectedly, disabled contrary to state, or sends a payload inconsistent with the catalog.

Accessibility roles, labels, selected state, disabled state, alerts, and the 375-pixel layout are assertions, not merely locator conveniences. Downloaded XML is checked against the advertised digest without including its contents in reports.

Alternative considered: screenshot-only validation. Screenshots are useful failure evidence but cannot reliably prove selected values, bounds, payloads, idempotency, or tenant persistence.

### 5. Make production smoke and paid gates explicit

The deployed runner accepts the base URL and bearer session through masked environment/configuration outside Git. It records only a run ID, non-secret catalog fingerprint, visible deployed revision when available, case IDs, statuses, sanitized errors, and exact created resource IDs needed for cleanup. Live screenshots/traces remain gitignored and must not capture authorization headers, storage state, uploaded XML, or secret values.

Default deployed smoke validates authentication, samples/catalog, one quadruped and one biped upload path, compatible/incompatible task visibility, all scene/object controls, bounded client behavior, save/reload/delete, and readiness text. It does not click Prepare or Start training. `--remote-preparation` runs at most one representative eligible preparation after all cheaper gates pass. `--remote-training` additionally requires an accepted current fingerprint and starts at most one fixed-profile job with a fresh idempotency key. Reports label unrequested gates `not-run-cost-gated`, not passed.

Alternative considered: automatically start all eight canonical remote cases. That duplicates existing runtime acceptance evidence, costs time/money, and delays feedback from form defects.

### 6. Use regression-first defect repair and structured evidence

A failure report contains its layer, case ID, selected catalog values, expected state, sanitized observed state, and reproduction command. Before repairing a product defect, the owning layer gains a minimal failing regression scenario. After the fix, the affected case/shard runs first, then all cheap layers, then the deployed no-cost smoke when deployment is in scope. Infrastructure/transient failures are classified separately and are not hidden by product retries.

Machine-readable JSON is authoritative; a Markdown summary is generated from it. Both report passed/failed/skipped/not-run counts, catalog coverage, timings, retries, created/deleted resource IDs, and cleanup/audit outcomes. Reports and browser media are gitignored; only durable test code and documentation are committed.

## Risks / Trade-offs

- [Catalog-derived tests could reproduce the same server bug in expected values] → Keep independent invariants for exact known task compatibility, scene/object IDs, capacity, and V1 eligibility counts in addition to generated rows.
- [Pairwise browser cases may miss a higher-order UI interaction] → Always include full happy paths for both robot types, every state transition, all individual controls, and promote any discovered interaction to a regression case.
- [Production mutation can consume tenant quotas or delete retained evidence] → Use dedicated test tenants, exact created-ID tracking, preflight quota checks, and explicit preservation versus cleanup mode; never delete user-owned preexisting rows.
- [Browser artifacts can leak tenant identity or authorization data] → Disable secret-bearing traces in deployed mode, sanitize structured output, keep artifacts gitignored, and fail secret scans before publication.
- [Parallel tests can become flaky through shared state] → Give workers isolated databases/tenants/artifact paths and serialize deployed mutation when tenant isolation is unavailable.
- [Remote preparation/training makes the fast signal slow] → Keep it outside the default gate, run only after cheap success, bound it to one representative case unless a separately approved matrix is requested, and report the coverage gap explicitly.
- [A test dependency increases image/CI weight] → Keep Playwright development-only, cache its browser binary in the test job, and exclude it from the production runtime image stage.

## Migration Plan

1. Add the coverage schema/generators and backend matrix without changing production behavior.
2. Expand component tests and make the existing SaaS image workflow run the full cheap gate in parallel shards.
3. Add the local full-stack Playwright job and verify deterministic cleanup and artifacts.
4. Add a manually triggered deployed smoke workflow with secrets supplied only by the runner environment and paid flags defaulting off.
5. Run the cheap matrix, repair discovered defects regression-first, deploy through the existing `debug-portal` GitOps path, and run the no-cost production smoke.
6. Enable one remote preparation/training canary only when explicitly requested; audit all jobs/instances afterward.

Rollback removes the new test jobs, dependency, and harness without data migration. Product repairs are independently revertible, but their regression tests remain unless the owning public requirement is deliberately changed through OpenSpec.

## Open Questions

- Which dedicated production test tenant/session should own deployed mutation and whether its created model/setup rows should be cleaned immediately or retained for short-lived manual inspection.
- Whether the first implementation run should stop after no-cost production smoke or include the separately cost-gated single preparation and training canary.
