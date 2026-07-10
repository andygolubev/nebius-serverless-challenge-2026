## 1. cert-manager installation (GitOps)

- [ ] 1.1 Pin the current stable cert-manager chart version and create
      `deploy/argocd/cert-manager-app.yaml`: ArgoCD child Application sourcing the
      `cert-manager` Helm chart from `https://charts.jetstack.io` with `crds.enabled=true`,
      destination namespace `cert-manager`, automated sync (prune + selfHeal) with retry,
      `CreateNamespace=true`
- [ ] 1.2 Verify the root app-of-apps path picks up the new child Application (same
      `deploy/argocd/` directory the root app watches)

## 2. Let's Encrypt issuers

- [ ] 2.1 Create `deploy/manifests/cert-manager/` kustomize directory with
      `letsencrypt-prod` ClusterIssuer (production ACME endpoint, email
      `andygolubevremit@gmail.com`, HTTP-01 solver with `ingressClassName: traefik`,
      private-key secret ref)
- [ ] 2.2 Add a `letsencrypt-staging` ClusterIssuer alongside it for rate-limit-safe
      troubleshooting
- [ ] 2.3 Create `deploy/argocd/cert-manager-issuers-app.yaml` syncing that directory, with a
      later sync-wave than the cert-manager app and automated sync + retry so cold bootstrap
      converges after CRDs exist

## 3. SaaS ingress TLS

- [ ] 3.1 Update `deploy/manifests/saas/ingress.yaml`: set
      `host: sim-policy-trainer-challenge.info`, add
      `tls` section with `secretName: saas-tls`, add annotation
      `cert-manager.io/cluster-issuer: letsencrypt-prod`, and refresh the stale header comment
- [ ] 3.2 Decide on and (if safe) enable the HTTP→HTTPS redirect per design Decision 4;
      otherwise record deferral in the design doc

## 4. Documentation

- [ ] 4.1 Update `sim2policy/infra/nebius/README.md`: document the domain, the manual DNS A
      record prerequisite (`sim-policy-trainer-challenge.info` → server public IP), and where
      to change the domain if it moves
- [ ] 4.2 Note in `saas.tfvars.example`/README that no firewall change is needed (80/443
      already open) and that DNS is managed at the registrar, not Terraform

## 5. Verification

- [ ] 5.1 After ArgoCD syncs: `kubectl get clusterissuer` shows both issuers `Ready`, and
      `kubectl -n saas get certificate saas-tls` reaches `Ready=True`
- [ ] 5.2 `curl -I https://sim-policy-trainer-challenge.info` (no `--insecure`) returns the
      SaaS app with a valid Let's Encrypt chain; browser shows no warning
- [ ] 5.3 Confirm renewal is armed: `kubectl -n saas describe certificate saas-tls` shows the
      expected renewal time (~60 days after issuance)
