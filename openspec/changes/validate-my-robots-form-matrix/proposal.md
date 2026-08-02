## Why

The **My Robots** workflow exposes many dependent choices—robot upload, robot type, task compatibility, scene presets, optional objects, numeric bounds, setup persistence, and preparation/training readiness—but the current tests do not provide one fast, reproducible signal that every visible control and supported combination works together. A generated validation matrix and a small production-browser smoke suite are needed now so defects can be found, repaired, and rechecked quickly without relying on ad-hoc manual experiments or unnecessarily starting costly training runs.

## What Changes

- Add an executable inventory of every control and user-visible state in the My Robots upload, validated-model, environment-builder, validated-setup, preparation, and training-start workflow.
- Generate exhaustive API/component scenarios from the server-owned catalog for both robot types, every compatible task, every scene preset, every optional object type, object-capacity rules, and each numeric default/minimum/maximum/invalid boundary.
- Add a compact pairwise browser matrix that covers every selectable value and compatibility edge with substantially fewer slow end-to-end cases, plus focused valid/invalid upload, download, delete, save, reload, prepare, retry, and start-action scenarios.
- Run independent matrix shards in parallel with isolated tenant/test data, deterministic case identifiers, bounded timeouts, structured failure evidence, and cleanup that never leaves cloud compute running.
- Add a production-safe smoke mode for `sim-policy-trainer-challenge.info` that verifies the deployed form and API contract in increasing-cost stages. It must not start training by default; remote preparation or training is an explicit, separately reported cost gate.
- Turn every discovered defect into a regression scenario, repair the owning frontend/backend/runtime boundary, rerun the affected shard, and finish with the complete cheap validation gate.
- Produce a concise machine-readable and human-readable coverage report showing tested combinations, skips, failures, cleanup, and the exact untested cost-gated paths.

## Capabilities

### New Capabilities

- `my-robots-validation-suite`: Defines the catalog-driven scenario matrix, parallel execution and isolation rules, browser smoke coverage, defect-regression workflow, reporting, and cleanup required to validate every My Robots form choice quickly.

### Modified Capabilities

None. The change verifies and restores conformance with the existing `saas-robot-assets`, `saas-environment-builder`, `saas-web-ui`, and custom-training requirements without changing their public contracts.

## Impact

- Frontend: `saas/frontend/src/views/MyRobots.tsx`, its component tests, test fixtures, and an end-to-end browser harness.
- Backend: robot upload, environment catalog/setup, preparation, and training-start contract tests plus catalog-derived parametrization.
- Automation: parallel test commands/CI jobs, deterministic artifacts, and an opt-in deployed smoke runner with bounded cleanup.
- Operations: test tenants and saved assets/setups created by live smoke checks must be uniquely labeled and removed; any explicitly enabled remote preparation/training must follow the repository's cost gates and instance cleanup policy.
- No breaking API, catalog, persistence, or training-profile change is intended.
