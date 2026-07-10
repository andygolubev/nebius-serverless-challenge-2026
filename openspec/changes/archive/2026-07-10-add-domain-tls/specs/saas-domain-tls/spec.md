## ADDED Requirements

### Requirement: SaaS site is served on the public domain over HTTPS
The system SHALL serve the SaaS application at `https://sim-policy-trainer-challenge.info`
through the cluster's Traefik ingress, using a certificate issued by Let's Encrypt that
browsers trust without warnings.

#### Scenario: Browser access via domain
- **WHEN** a user opens `https://sim-policy-trainer-challenge.info`
- **THEN** the SaaS application responds over TLS with a valid, publicly trusted certificate
  whose subject covers `sim-policy-trainer-challenge.info`

#### Scenario: Certificate chain validates
- **WHEN** a TLS client (e.g. `curl`) connects to the domain on port 443 without
  `--insecure`
- **THEN** the connection succeeds with a certificate chain issued by Let's Encrypt

### Requirement: Certificates are issued and renewed automatically
The system SHALL use cert-manager with a Let's Encrypt `ClusterIssuer` (ACME HTTP-01,
registration email `andygolubevremit@gmail.com`) so that certificate issuance and renewal
require no operator action.

#### Scenario: Initial issuance
- **WHEN** the ingress carrying the `cert-manager.io/cluster-issuer` annotation is synced and
  DNS for the domain resolves to the server
- **THEN** cert-manager completes the HTTP-01 challenge and stores a valid certificate in the
  ingress's TLS secret, and the `Certificate` resource reports `Ready=True`

#### Scenario: Automatic renewal
- **WHEN** the certificate approaches expiry (within cert-manager's renewal window)
- **THEN** cert-manager renews it and rotates the TLS secret without manual intervention or
  downtime

### Requirement: TLS stack is GitOps-managed
cert-manager, its issuers, and the ingress TLS configuration SHALL be declared in Git and
reconciled by ArgoCD through the existing app-of-apps, so a fresh cluster bootstrap converges
to a working HTTPS setup with no imperative steps.

#### Scenario: Fresh bootstrap converges
- **WHEN** the saas-server VM is re-provisioned from scratch and the root ArgoCD application
  syncs the repository
- **THEN** cert-manager installs, the ClusterIssuer becomes ready (after automated retries if
  CRDs lag), and the site certificate is issued without any manual kubectl or helm commands

#### Scenario: Rollback by revert
- **WHEN** the change's Git commit is reverted
- **THEN** ArgoCD prunes cert-manager and the TLS configuration, returning the ingress to its
  previous (host-less, default-cert) state
