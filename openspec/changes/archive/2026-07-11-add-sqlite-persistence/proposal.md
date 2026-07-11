# add-sqlite-persistence

## Why

The SaaS backend keeps users, sessions, jobs, and artifact manifests in process memory
(`AuthStore`/`JobStore`), so every pod restart or image rollout logs all users out and erases job
history. With GitOps-driven deploys this happens frequently, breaking returning-user flows and any
agent testing that reuses a bearer token across deploys.

## What Changes

- Replace the in-memory `AuthStore` and `JobStore` internals with a SQLite database stored on a
  Kubernetes PersistentVolumeClaim, keeping the existing store interfaces unchanged.
- Persist users, sessions, jobs, and artifact manifests; pending one-time codes and rate-limit
  windows remain ephemeral (they are short-lived by design and safe to lose on restart).
- Add a PVC to the SaaS deployment manifests and switch the Deployment to the `Recreate` strategy
  so the ReadWriteOnce volume is released before the new pod starts.
- Add a `SAAS_DB_PATH` environment variable selecting the SQLite file location, defaulting to an
  ephemeral path for local development and tests.

## Capabilities

### New Capabilities

- `saas-data-persistence`: Durable storage of tenant data (users, sessions, jobs, artifact
  manifests) in SQLite on a cluster volume, surviving pod restarts and redeploys.

### Modified Capabilities

- `saas-email-auth`: Sessions and tenant accounts SHALL survive backend restarts; a valid,
  unexpired session token issued before a restart remains valid after it.

## Impact

- Code: `saas/backend/app/store.py` (SQLite-backed stores), `saas/backend/app/main.py` (store
  wiring/config), `saas/backend/tests/` (store and auth tests against SQLite).
- Deployment: `deploy/manifests/saas/` (new PVC manifest, volume mount, `Recreate` strategy,
  `SAAS_DB_PATH` env var).
- Dependencies: Python stdlib `sqlite3` only; no new packages, no external database service.
