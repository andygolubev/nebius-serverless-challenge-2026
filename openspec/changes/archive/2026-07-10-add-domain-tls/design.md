## Context

The SaaS app runs on a single-node k3s cluster on the Nebius `saas-server` VM
(public IP `89.169.125.243`) and is exposed through k3s's built-in Traefik ingress controller.
Delivery is GitOps: a root ArgoCD app-of-apps (created by cloud-init) watches `deploy/argocd/`
and syncs child Applications such as `deploy/argocd/saas-app.yaml`, which deploys the kustomize
tree at `deploy/manifests/saas/`.

Current state:
- `deploy/manifests/saas/ingress.yaml` has no `host` and no `tls` section; Traefik serves its
  default self-signed certificate on 443.
- The firewall (`sim2policy/infra/nebius/saas.tf`) already allows 80 and 443 from `0.0.0.0/0`
  (80 was opened specifically for ACME/redirect), so no Terraform network change is needed.
- The domain `sim-policy-trainer-challenge.info` has been registered and its A record already
  points to `89.169.125.243` (managed manually at the registrar; DNS is not in Terraform).

Constraints:
- Everything on the cluster must be GitOps-managed through the existing app-of-apps pattern —
  no imperative `kubectl`/`helm` steps that cloud-init or an operator must remember to run.
- ACME registration email: `andygolubevremit@gmail.com`.

## Goals / Non-Goals

**Goals:**
- Serve the SaaS site at `https://sim-policy-trainer-challenge.info` with a browser-trusted
  Let's Encrypt certificate.
- Certificates are issued and renewed automatically by cert-manager with no operator action.
- cert-manager itself is installed and versioned via ArgoCD (declarative, reproducible on a
  fresh VM re-provision).

**Non-Goals:**
- Managing DNS records in Terraform (the registrar record is maintained manually).
- `www.` or wildcard certificates (single apex host only; wildcard would require DNS-01).
- Changing the app, service, firewall, or SSH-tunnel management posture.
- Certificate monitoring/alerting beyond what cert-manager provides out of the box.

## Decisions

### Decision 1: cert-manager via an ArgoCD child Application using the Jetstack Helm chart

Add `deploy/argocd/cert-manager-app.yaml`, a child Application picked up by the existing root
app-of-apps. It sources the `cert-manager` Helm chart from `https://charts.jetstack.io` with a
pinned `targetRevision` (current stable, e.g. `v1.18.x`) and `crds.enabled=true`, deployed into
a `cert-manager` namespace with automated sync (prune + self-heal), matching the saas app's
sync policy.

- *Why Helm chart over static manifests vendored into the repo:* the chart is the upstream
  supported install path, pins cleanly via `targetRevision`, and avoids checking ~30k lines of
  generated YAML into the repo.
- *Why a child Application over installing in cloud-init:* keeps cloud-init minimal and makes
  the install reproducible/upgradable through Git like everything else; a VM rebuild converges
  automatically.

### Decision 2: HTTP-01 challenge through Traefik, `ClusterIssuer` in Git

Add `deploy/manifests/cert-manager/` (kustomize) containing a `ClusterIssuer` named
`letsencrypt-prod` using the Let's Encrypt production ACME endpoint, email
`andygolubevremit@gmail.com`, and an HTTP-01 solver with `ingressClassName: traefik`. A second
issuer `letsencrypt-staging` is included for troubleshooting without burning production rate
limits. A sibling child Application `deploy/argocd/cert-manager-issuers-app.yaml` syncs this
directory.

- *Why HTTP-01 over DNS-01:* port 80 is already open, the registrar's DNS has no API
  integration in this project, and only a single non-wildcard host is needed.
- *Why ClusterIssuer over namespaced Issuer:* the certificate lives in the `saas` namespace
  while cert-manager runs in `cert-manager`; a ClusterIssuer avoids per-namespace duplication
  if other apps need certs later.
- *Ordering:* the ClusterIssuer CRD only exists after the cert-manager app syncs. Both child
  apps use automated sync with retry (and the issuers app gets a later sync-wave annotation),
  so ArgoCD converges even on a cold bootstrap where the first issuer sync fails.

### Decision 3: TLS declared on the existing Ingress via annotation

Update `deploy/manifests/saas/ingress.yaml`:
- `spec.rules[0].host: sim-policy-trainer-challenge.info`
- `spec.tls: [{hosts: [sim-policy-trainer-challenge.info], secretName: saas-tls}]`
- annotation `cert-manager.io/cluster-issuer: letsencrypt-prod`

cert-manager's ingress-shim watches the annotation, creates the `Certificate`, solves the
HTTP-01 challenge via a temporary ingress on Traefik's `web` entrypoint, stores the signed cert
in the `saas-tls` secret, and renews it automatically ~30 days before expiry.

- *Why ingress-shim annotation over an explicit `Certificate` resource:* one fewer manifest,
  and the certificate's lifecycle is tied to the ingress that uses it. An explicit Certificate
  adds value only when multiple ingresses share a cert, which is not the case here.
- The domain is hard-coded in the ingress manifest (and issuer docs); with a single
  environment and kustomize already in place, introducing a templating layer for one value is
  not worth the indirection. The README records it as the place to change.

### Decision 4: HTTP→HTTPS redirect stays with Traefik defaults

k3s's bundled Traefik keeps the `web` (80) entrypoint reachable, which HTTP-01 requires. A
global 80→443 redirect is added only if it does not interfere with ACME solving (Traefik's
redirect happens after cert-manager's solver ingress matches, so it is safe); implemented as a
`traefik.ingress.kubernetes.io/router.entrypoints: web,websecure` + redirect middleware or the
HelmChartConfig redirect option. This is a polish task, not a blocker.

## Risks / Trade-offs

- [Let's Encrypt production rate limits (5 failures/hour, 50 certs/week per domain)] →
  staging issuer included; verify with staging first if the first production attempt fails.
- [DNS propagation incomplete when the ingress syncs] → cert-manager retries challenges
  automatically with backoff; no manual intervention needed, just wait.
- [Cold-bootstrap ordering: ClusterIssuer applied before CRDs exist] → ArgoCD automated sync
  retry + sync-wave ordering; degraded state is temporary and self-heals.
- [ACME account/email tied to a personal Gmail] → acceptable for a challenge project; email
  only receives expiry warnings, which cert-manager renewal makes moot.
- [Site becomes host-based; requests to the bare IP no longer match the ingress rule] →
  acceptable and arguably desirable; the IP-based URL was never the public entry point.

## Migration Plan

1. Merge manifests; ArgoCD root app picks up the two new child Applications automatically.
2. cert-manager installs; issuers sync (may retry once); ingress update triggers issuance.
3. Verify: `kubectl get certificate -n saas` shows `Ready=True`, then
   `curl -I https://sim-policy-trainer-challenge.info` returns the app with a valid chain.
4. Rollback: revert the Git commit; ArgoCD prunes cert-manager and restores the host-less
   ingress (site returns to self-signed on IP). The `saas-tls` secret is pruned with it.

## Open Questions

- ~~Exact cert-manager chart version to pin~~ — resolved: `v1.21.0` (latest stable at
  implementation time).
- ~~Whether to enable the 80→443 redirect~~ — resolved: enabled per-router, not globally. The
  saas ingress listens on `web,websecure` with a namespace-scoped Traefik `redirectScheme`
  Middleware; cert-manager's solver ingress is a separate, more specific router without the
  middleware, so ACME challenges are never redirected.
