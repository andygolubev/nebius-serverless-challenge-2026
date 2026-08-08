# GitOps state

Everything ArgoCD reconciles onto the `saas-server` k3s cluster. **Git is the source of truth**: a
merge to `main` is the only action needed to change what runs, and a manual cluster edit is reported
OutOfSync and reverted by self-heal.

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the reasoning behind this layout.

## Layout

```
deploy/
├── argocd/                          child Applications picked up by the root app-of-apps
│   ├── saas-app.yaml                the tenant SaaS app        → deploy/manifests/saas
│   ├── cert-manager-app.yaml        Jetstack Helm chart v1.21.0 → cert-manager namespace
│   └── cert-manager-issuers-app.yaml ACME issuers              → deploy/manifests/cert-manager
├── manifests/
│   ├── saas/                        Namespace, PVC, Deployment, Service, Ingress, redirect middleware
│   └── cert-manager/                letsencrypt-prod and letsencrypt-staging ClusterIssuers
└── tests/
    ├── assert-saas-gitops-workflow.sh    the image workflow's branch/stale-ref/push contract
    └── assert-saas-production-email.sh   production must not run mock email delivery
```

The **root** Application is created by cloud-init on the server
(`sim2policy/infra/nebius/cloud-init/saas-server.yaml.tftpl`) and watches `deploy/argocd`. Every
repository-owned Application declares `targetRevision: main`.

## How an image reaches the cluster

1. A qualifying push to `main` triggers `.github/workflows/saas-image.yml`.
2. The workflow builds the SaaS image and pushes it to the Nebius Registry with an immutable
   commit-SHA tag, authenticating via `docker login --password-stdin` with a `registry.pusher`
   service-account credential.
3. On success it verifies that `main` still resolves to the build SHA, then commits
   `kustomize edit set image` into `manifests/saas/kustomization.yaml` and pushes with `[skip ci]`.
   A stale build therefore cannot overwrite a newer tag, and the bump cannot trigger itself.
4. ArgoCD detects the drift and syncs. Pods pull through the `nebius-registry` `imagePullSecret`.

Tag and manual-dispatch builds publish an image without changing production GitOps state.

> **Gotcha.** If the live `saas` Application carries a `kustomize.images` override in its spec, that
> override silently wins over the tag committed here and the deployment appears frozen on an old
> image. Check the live Application before debugging the workflow.

## Deployment shape

Durable SaaS state is SQLite on the ReadWriteOnce `saas-data` PVC (k3s `local-path`, 1 GiB,
node-local). That forces `replicas: 1` and `strategy: Recreate` — the old pod must release the
volume before the replacement schedules, and a rolling update would deadlock on the attach. Seconds
of rollout downtime is the accepted trade.

Configuration arrives from two Kubernetes Secrets, both reconciled on the server from MysteryBox by
root-owned systemd units, never from Git:

- `saas-nebius` (`optional: true`) — the whole `NEBIUS_*` / `AWS_*` / `SIM2POLICY_*` /
  `CUSTOM_ROBOT_*` orchestration contract plus `SAAS_ANALYTICS_IP_SALT`. It is optional so the
  manifest syncs in any order; without it the app falls back to its built-in `mock` backend.
  `SAAS_ORCHESTRATION_BACKEND` deliberately has **no** explicit `env` entry, because an explicit
  `env` would override `envFrom`.
- `saas-smtp` (`optional: false`) — the seven `SAAS_SMTP_*` keys. Non-optional so a rollout cannot
  silently start without email credentials.

The pod mounts `/mnt/cloud-metadata` as a directory, not the `token` file inside it: Nebius rotates
the `..data` symlink target atomically, and a file-level bind would pin a stale inode that expires
with the old token. It runs non-root, read-only root filesystem, all capabilities dropped.

## TLS

`ingress.yaml` carries `cert-manager.io/cluster-issuer: letsencrypt-prod`; cert-manager's
ingress-shim creates the `Certificate`, solves HTTP-01 through Traefik's `web` entrypoint, stores the
result in `saas-tls`, and renews automatically. The router listens on `web,websecure` with a
namespace-scoped `redirectScheme` middleware; cert-manager's solver ingress is a separate, more
specific router without that middleware, so ACME challenges are never redirected. There is
deliberately no `router.tls` annotation — it would force the router TLS-only and break the plain-HTTP
match the redirect needs.

A fresh VM converges to working HTTPS with no imperative `kubectl` or `helm` step. On a cold
bootstrap the issuers may fail their first sync before the CRDs exist; ArgoCD's automated retry
resolves it. Reverting the commit prunes cert-manager and returns the ingress to its previous state.

## Verifying a rollout

The k3s API and ArgoCD UI are not public. Reach them over an SSH tunnel (see
[`saas/README.md`](../saas/README.md)); `kubectl` on the box itself requires `sudo`. Verify a
deployment through the workflow run, the GitOps tag commit, the ArgoCD sync, the rolled pod, and the
public endpoint — never infer it from a push.
