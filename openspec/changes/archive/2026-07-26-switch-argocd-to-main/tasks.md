## 1. Repository GitOps source

- [x] 1.1 Record the `main`-only commit/push policy in `AGENTS.md`.
- [x] 1.2 Repoint repository-owned Argo CD child Applications to `main`.
- [x] 1.3 Repoint OpenTofu/bootstrap defaults, example input, and configured local input to `main`.

## 2. Repository verification and delivery

- [x] 2.1 Validate YAML and confirm all tracked Argo CD source references use `main`.
- [x] 2.2 Record the repository update in `IMPLEMENTATION_LOG.MD`, commit it on `main`, and push only `origin/main`.

## 3. Deferred live-cluster cutover

- [x] 3.1 Independently verify the SaaS server's changed SSH host key before connecting.
- [x] 3.2 Manually repoint the live root Argo CD Application to `main`, then refresh and sync it.
- [x] 3.3 Verify the root and child Applications are Synced and Healthy and the SaaS workload is healthy.
