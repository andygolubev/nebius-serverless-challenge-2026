## Why

The SaaS site is currently served on the raw server IP (89.169.125.243) with Traefik's default
self-signed certificate, so browsers show a security warning and there is no stable, shareable
address. A domain (`sim-policy-trainer-challenge.info`) has been purchased and its DNS A record
already points at the server, so the remaining work is to serve the site on that hostname with a
trusted, auto-renewing Let's Encrypt certificate.

## What Changes

- Install cert-manager into the k3s cluster as a new ArgoCD child Application (GitOps-managed,
  consistent with the existing app-of-apps pattern).
- Add a Let's Encrypt `ClusterIssuer` using the HTTP-01 challenge (solved through the existing
  Traefik ingress on port 80, which the firewall already allows) with ACME registration email
  `andygolubevremit@gmail.com`.
- Update the SaaS `Ingress` to declare the host `sim-policy-trainer-challenge.info`, reference a
  cert-manager-managed TLS secret, and carry the issuer annotation so the certificate is obtained
  and renewed automatically.
- Surface the domain as configuration (Terraform variable / kustomize value) rather than
  hard-coding it in multiple places where practical.

No firewall or Terraform network changes are required: ports 80 (ACME/redirect) and 443 (HTTPS)
are already open to the internet in `sim2policy/infra/nebius/saas.tf`.

## Capabilities

### New Capabilities
- `saas-domain-tls`: Serving the SaaS site on a public domain with an automatically issued and
  renewed Let's Encrypt certificate (cert-manager, HTTP-01 via Traefik).

### Modified Capabilities

<!-- none: existing specs do not cover ingress/TLS behavior at requirement level -->

## Impact

- `deploy/manifests/saas/ingress.yaml` — add host, TLS section, cert-manager annotation.
- `deploy/manifests/cert-manager/` (new) — cert-manager installation + `ClusterIssuer` manifests.
- `deploy/argocd/` — new child Application for cert-manager.
- `sim2policy/infra/nebius/README.md` / `saas.tfvars.example` — document the domain and DNS
  prerequisite.
- Dependencies: cert-manager (pinned release manifests or Helm chart), Let's Encrypt production
  ACME endpoint. No application code changes.
