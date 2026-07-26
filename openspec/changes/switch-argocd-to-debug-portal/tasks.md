## 1. Repository GitOps source

- [x] 1.1 Add the temporary `main` commit/push prohibition to `AGENTS.md`.
- [x] 1.2 Repoint repository-owned Argo CD child Applications to `debug-portal`.
- [x] 1.3 Repoint OpenTofu/bootstrap defaults, example input, and configured local input to `debug-portal`.

## 2. Repository verification and delivery

- [x] 2.1 Validate YAML and confirm all tracked Argo CD source references use `debug-portal`.
- [x] 2.2 Record the repository update in `IMPLEMENTATION_LOG.MD`, commit it on `debug-portal`, and push only `origin/debug-portal`.

## 3. Deferred live-cluster cutover

- [ ] 3.1 Independently verify the SaaS server's changed SSH host key before connecting.
- [ ] 3.2 Manually repoint the live root Argo CD Application to `debug-portal`, then refresh and sync it.
- [ ] 3.3 Verify the root and child Applications are Synced and Healthy and the SaaS workload is healthy.
