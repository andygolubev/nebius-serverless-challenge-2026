## Context

The My Robots page spans four boundaries: React form behavior, FastAPI validation and persistence, asynchronous preparation/training state, and the deployed browser/API path. Existing tests cover representative uploads, compatibility rules, scenes, object rejection, and several lifecycle states, but their fixtures are hand-written and no single run proves that every current catalog value appears in a scenario. The live form also hides the environment builder until an upload succeeds, so a shallow page smoke misses most controls.

The current server-owned catalog has two declared robot types; five compatible robot-type/task pairs; four scenes; four optional object types; seven bounded parameters per object; and a six-total-object limit. The original V1 gate admitted only eight robot/task/scene combinations and rejected every tenant-added object. Live UI testing proved that the builder still saves the rejected configurations, producing `Unsupported Task`, `Unsupported Scene`, and `Optional Objects Not Supported` cards. The accepted contract is now that every catalog-valid setup the builder saves is preparation- and training-capable. Exhaustively multiplying every possible object list and continuous numeric value is neither finite nor useful, so cheap layers remain exhaustive over discrete choices and bounds while the slow browser layer remains pairwise.

Constraints include tenant ownership, 20 active models and 50 active setups per tenant, secret bearer sessions, soft deletion, asynchronous remote jobs, and the requirement to stop/delete cloud compute after use. Generated run evidence is local and gitignored. The existing public API remains the system under test; no test-only production endpoint or authentication bypass is introduced.

## Goals / Non-Goals

**Goals:**

- Prove that every visible My Robots control and every server-advertised discrete choice has an executable scenario.
- Exhaustively validate compatible and incompatible robot/task edges, all scenes, all object types, parameter boundaries, object capacity, persistence, ownership, and readiness projection in cheap tests.
- Exercise the same workflow through a real browser with a compact pairwise matrix and one end-to-end happy path per important state transition.
- Run independent cheap cases in parallel, aggregate all failures, and leave deterministic evidence that makes each failure directly reproducible.
- Separate no-cost validation from remote preparation and training so a skipped cost gate is reported honestly instead of being treated as passed.
- Make defect repair regression-first and require the relevant shard plus the full cheap gate to pass afterward.
- Make every valid builder configuration trainable through server-owned composition and fixed policy code, including Recover From Fall, all four terrain presets, and all bounded optional primitives.

**Non-Goals:**

- Infer morphology from the declared biped/quadruped radio choice; the current contract treats robot type as validated tenant metadata.
- Exhaust every ordering or repetition of up to six optional objects, or every real number inside a parameter range.
- Add arbitrary task code, uploaded scenes, meshes, plugins, scripts, URLs, or tenant-defined reward logic.
- Add a production test backdoor, expose credentials in reports, or make paid training part of ordinary CI.
- Use this form suite as proof of policy convergence; remote preparation proves compatibility and training completion reports measured outcomes separately.

### Unsupported-state inventory and expanded capability mapping

The former readiness gate emitted three user-visible unsupported categories. Each is removed for catalog-valid setup payloads and retained only in historical regression coverage:

| Former message | Builder configurations that produced it | Expanded contract |
| --- | --- | --- |
| `Unsupported Task` | quadruped + Recover From Fall + any scene/object combination | bounded fallen-state reset, recovery reward/success criteria, evaluation, checkpoint reload, and rendering |
| `Unsupported Scene` | either robot family + Stand Balance/Walk Forward, or quadruped Recover From Fall, on Hurdle Course or Step Course | deterministic server-owned Hurdle/Step terrain composition with preset objects included in the six-object bound |
| `Optional Objects Not Supported` | any compatible model/task/scene plus one or more tenant-selected Box, Ramp, Hurdle, or Step primitives | strict normalized primitive schema and deterministic server-owned composition of bounded position, yaw, width, depth, and height |

Concrete deployed reproductions include biped Stand Balance on Hurdle Course with an added Step, quadruped Recover From Fall on Step Course with an added Hurdle, and quadruped Stand Balance on Flat Arena with an added Ramp. All are valid builder configurations and therefore must project `not_prepared`, `preparing`, `preparation_failed`, or `ready`, never an unsupported-capability state.

## Decisions

### 1. Generate one canonical case inventory from server-owned contracts

Backend parametrization will read the real serialized environment catalog and canonical sample metadata, then emit stable case identifiers. The baseline inventory includes:

- both canonical sample uploads through both radio-control paths, while asserting the contract-defined outcome rather than attempting morphology inference;
- all 5 compatible robot/task pairs across all 4 scenes (20 no-optional-object setup cases);
- each of the 4 optional object types at defaults for every base setup (80 one-object cases), with readiness reasons derived from the real eligibility contract;
- each object parameter at default, minimum, maximum, just below minimum, just above maximum, empty/non-numeric browser state, and non-finite API input where representable;
- exact capacity and one-over-capacity cases for all four scene preset sizes; and
- the eight formerly V1-eligible combinations as regression anchors plus all 92 formerly unsupported catalog-valid combinations, with ineligibility reserved for genuine invalid/disabled/source-unavailable states.

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

### 7. Admit capabilities from the normalized builder contract

The control plane no longer maintains a second fixed allowlist narrower than the environment catalog. Admission requires a supported declared robot family, a task compatible with that family, a known scene, a normalized object list within the catalog bounds, an enabled runtime, and a current accepted preparation fingerprint. The normalized training input carries all resolved preset and custom primitive objects. The runtime independently validates the closed schema, finite numeric bounds, source values, object count, and known identifiers before composing MuJoCo geometry.

The scene/reward/schema versions change with this expansion so historical accepted preparations cannot silently authorize a materially different world. Fingerprints continue to bind robot digest, setup digest, immutable runtime image, adapter, reward, and preparation-profile versions. No tenant MJCF world element, code, asset, URL, mesh, texture, plugin, or reward expression is accepted.

Recover From Fall is quadruped-only because that is the compatibility edge exposed by the catalog. Reset samples a bounded side-fallen free-root orientation and bounded joint noise; falling is not terminal for this task. Success requires regaining minimum height and uprightness with bounded root speed. Stand Balance and Walk Forward retain their existing reset and termination behavior.

The UI treats a completed job as durable setup history: it links to that result and requires explicit confirmation before requesting a new paid run. Idempotency still protects a single submission, while active and daily quotas remain authoritative server responses.

## Risks / Trade-offs

- [Catalog-derived tests could reproduce the same server bug in expected values] → Keep independent invariants for exact known task compatibility, scene/object IDs, capacity, the eight historical V1 anchors, and the complete 100-case preparation-admission count in addition to generated rows.
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
