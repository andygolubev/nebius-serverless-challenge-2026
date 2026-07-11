# add-sqlite-persistence — Tasks

## 1. SQLite store layer

- [ ] 1.1 Add a small DB module in `saas/backend/app/` that opens the SQLite connection from
  `SAAS_DB_PATH` (default local file), enables WAL + `synchronous=NORMAL`, and creates the
  `users`, `sessions`, `jobs`, and `artifacts` tables with `CREATE TABLE IF NOT EXISTS`
- [ ] 1.2 Rewrite `JobStore` in `saas/backend/app/store.py` to read/write jobs and artifact
  manifests from SQLite (serialize `Job`/`ArtifactManifest` fields to columns or JSON), keeping
  `put/get/list/set_artifacts/get_artifacts` signatures and tenant-isolation behavior unchanged
- [ ] 1.3 Rewrite `AuthStore` users and sessions to SQLite (`ensure_user`, `put_session`,
  `get_session` with expiry cleanup, `delete_session`), keeping pending codes and rate-limit
  windows in memory as today
- [ ] 1.4 Wire the DB path/connection setup into app startup in `saas/backend/app/main.py`

## 2. Tests

- [ ] 2.1 Point tests at a temp-file database (fixture setting `SAAS_DB_PATH` to a tmp path) and
  confirm the existing auth and job test suites pass unchanged
- [ ] 2.2 Add restart-survival tests: create user/session/job/artifacts, reopen the stores against
  the same file, assert the session still resolves and jobs/artifacts are returned with tenant
  isolation intact

## 3. Deployment manifests

- [ ] 3.1 Add a 1Gi ReadWriteOnce PVC manifest in `deploy/manifests/saas/` (k3s `local-path`
  StorageClass) and register it in the kustomization
- [ ] 3.2 Update `deploy/manifests/saas/deployment.yaml`: mount the PVC at `/data`, set
  `SAAS_DB_PATH=/data/saas.db`, and switch the Deployment strategy to `Recreate`

## 4. Verification & docs

- [ ] 4.1 After ArgoCD syncs, verify end-to-end on the cluster: log in, submit a job, delete the
  pod, confirm the same token still works and the job list is intact
- [ ] 4.2 Update `saas/README.md` with the `SAAS_DB_PATH` variable and persistence notes
