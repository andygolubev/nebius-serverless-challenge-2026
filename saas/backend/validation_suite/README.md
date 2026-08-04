# My Robots validation evidence

`validation_suite` owns the executable catalog matrix and the schema used to merge cheap-layer
test evidence. Generated evidence belongs under the repository-root `.form-validation-runs/`
directory, which is gitignored because deployed screenshots and diagnostics may contain
tenant-visible data.

## Stable case IDs

Case IDs are lowercase colon-separated identities such as
`api:setup:biped:walk-forward:flat-arena:none`. They name the layer, scenario family, and catalog
selection without including a tenant, bearer token, opaque storage identity, or uploaded model
content. IDs are deterministically assigned to a shard by the SHA-256 of the complete ID.

The matrix currently enforces these independent public-contract invariants:

- 2 declared robot types and 5 compatible robot/task edges;
- 4 scenes and 4 optional primitive object types;
- 7 parameters for each object type (28 definitions total);
- 20 valid no-object plus 80 valid one-default-object setup cases;
- 4 exact and 4 one-over scene-capacity cases; and
- 8 V1 preparation-eligible robot/task/scene combinations.

## Result schema

The authoritative JSON report contains:

- `schema_version`, `run_id`, `generated_at`, and a SHA-256 `catalog_fingerprint`;
- one result per stable `case_id`, with `layer`, status, duration, sanitized diagnostic, and the
  local evidence filename;
- pass/fail/error/skip totals plus duplicate- and optional expected-case detection;
- remote preparation/training states, which default to `not-run-cost-gated`;
- exact non-secret created/deleted resource IDs and cleanup status.

The Markdown report is generated from that JSON. Reports never embed screenshots, downloads,
authorization headers, tokens, email codes, uploaded XML, secret selectors, storage keys, or raw
provider responses.

## Commands

From `saas/backend`:

```bash
python -m validation_suite.matrix --output ../../.form-validation-runs/expected.json
python -m validation_suite.report merge \
  --expected ../../.form-validation-runs/expected.json \
  --junit ../../.form-validation-runs/backend.xml \
  --junit ../../.form-validation-runs/frontend.xml \
  --junit ../../.form-validation-runs/browser.xml \
  --run-id local-YYYYMMDDTHHMMSSZ \
  --output ../../.form-validation-runs/report.json \
  --markdown ../../.form-validation-runs/report.md
python -m validation_suite.report scan ../../.form-validation-runs
```

A scan failure prints filenames and finding categories only; it never echoes the matched secret or
private model content.
