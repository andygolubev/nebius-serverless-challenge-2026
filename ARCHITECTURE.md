# Sim2Policy architecture

Sim2Policy is a configuration-driven reinforcement-learning template that turns a local or Nebius
Serverless AI training job into durable checkpoints, evaluation metrics, reports, and rollout
media. Track B (Gymnasium MuJoCo + Stable-Baselines3) is the dependable baseline. Track A (MuJoCo
Playground/Brax PPO on MJX) is isolated behind its own dependency and container target so it cannot
break Track B.

Two planes sit on top of the same durable run tree. The **data plane** trains policies as ephemeral
Serverless AI Jobs and writes artifacts to S3. The **control plane** (added by `add-saas-server`) is
an always-on `saas-server` VM running a single-node k3s cluster and ArgoCD, which GitOps-deploys a
tenant-facing SaaS app whose image is built by GitHub Actions and pulled from the Nebius registry.
The training path is unchanged; the control plane is a new, isolated front door.

```mermaid
flowchart LR
    subgraph data["Data plane (training)"]
      U["User, Make, or demo API"] --> C["Validated YAML config and CLI overrides"]
      C --> J["Local process or Nebius Serverless AI Job"]
      J --> B{"Backend adapter"}
      B -->|Track B| S["SB3 + Gymnasium MuJoCo"]
      B -->|Track A| M["Playground/Brax + MJX"]
      S --> R["Canonical runs/<run-id> tree"]
      M --> R
      R --> O["S3-compatible object storage"]
      R --> E["Deterministic evaluation and reporting"]
      R --> V["Headless rollout rendering and montage"]
      E --> O
      V --> O
      A["FastAPI demo layer"] --> U
      A --> O
    end

    subgraph control["Control plane (SaaS delivery)"]
      GH["GitHub Actions CI"] --> RG["Nebius registry image"]
      GIT["Git deploy/ manifests"] --> AR["ArgoCD on saas-server (k3s)"]
      RG --> AR
      MB["MysteryBox: GitHub, registry, artifact, SMTP, job-pull creds"] --> SYNC["Root-owned secret reconcilers"]
      SYNC --> KS["Kubernetes Secrets"]
      MB -->|"Git repository token"| AR
      AR --> SAAS["Tenant SaaS app (FastAPI + React)"]
      KS --> SAAS
      TEN["Tenants"] -->|"HTTPS 443"| SAAS
      SAAS --> DB["SQLite on saas-data PVC"]
      SAAS --> MAIL["Mailjet SMTP relay"]
      SAAS --> API["Nebius Serverless AI API"]
      API --> J
      OP["Operator"] -->|"SSH tunnel"| AR
    end

    T["OpenTofu"] --> I["Nebius registry, bucket, least-privilege identity, saas-server"]
    I --> J
    I --> O
    I --> AR
```

## Main boundaries

- `openspec/` is the planning source of truth: proposals explain intent, designs record decisions,
  specs define behavior, and task files track verified implementation.
- `sim2policy/src/sim2policy/` contains shared configuration, run lifecycle, storage, evaluation,
  rendering, telemetry, reporting, API, and backend-specific trainer adapters.
- `sim2policy/configs/` holds reproducible environment/run contracts and hosted-demo presets.
- `sim2policy/Dockerfile` has backend-isolated `sb3` and `mjx` runtime targets.
- `.github/workflows/training-runtime-images.yml` builds both targets on CPU runners, validates
  backend-specific imports, publishes target-qualified immutable tags (`sb3-<sha>` / `mjx-<sha>`),
  and only then advances the `sb3-runtime` / `mjx-runtime` compatibility tags.
- `sim2policy/jobs/submit.sh` is the validated Nebius job boundary; it constructs argument arrays,
  enforces a timeout, and accepts MysteryBox secret selectors without printing their values.
- `sim2policy/infra/nebius/` uses OpenTofu to provision the container registry, bounded/versioned
  artifact bucket, and least-privilege artifact service account. Serverless jobs remain explicit
  submissions, not persistent infrastructure resources. `saas.tf` adds the always-on `saas-server`
  VM, dedicated orchestration identity, scoped MysteryBox secrets/read permits, and a
  `nebius_vpc_v1_security_group` that admits only 22/443/80;
  `cloud-init/saas-server.yaml.tftpl` bootstraps k3s, ArgoCD, and root-owned Secret reconcilers.
- `saas/` is the tenant-facing SaaS application: a FastAPI backend (`saas/backend/`) exposing the
  authenticated job API with verified-email tenant scoping, SQLite persistence, and pluggable mock
  or Nebius orchestration, plus a React + Vite + TypeScript frontend (`saas/frontend/`). One
  multi-stage image serves API and UI.
- `deploy/` holds the GitOps state ArgoCD reconciles: `deploy/argocd/` (app-of-apps `Application`s)
  and `deploy/manifests/saas/` (Deployment, SQLite PVC, Service, Traefik Ingress, and immutable
  kustomize image mapping).
- `.github/workflows/saas-image.yml` builds the SaaS image and pushes it to the Nebius registry,
  authenticating with a `registry.pusher` service-account credential via `docker login --password-stdin`.
  A successful `main` build commits the immutable image tag to the kustomization after verifying
  that `main` has not advanced, so ArgoCD deploys the exact build without an operator override.
- `runs/<run-id>/` is canonical while a process runs. `checkpoints/`, `tensorboard/`, `videos/`, and
  `report/` map to the same subpaths at `s3://<bucket>/sim2policy/<run-id>/`, which is canonical
  across ephemeral jobs. A checkpoint is uploaded fully before `latest.json` is advanced.
- `sim2policy/web/` and the FastAPI package provide the thin demo surface. Run status and artifact
  manifests live in the same durable run tree, keeping API instances stateless.

## SaaS control plane

The control plane keeps a durable front door running without hand-run `make` commands. A single
`saas-server` CPU VM self-bootstraps a one-node **k3s** cluster and **ArgoCD** through cloud-init.
**Git is the source of truth**: ArgoCD syncs `deploy/` and self-heals drift, so a merge is the only
action needed to change what runs. The SaaS app image is built by **GitHub Actions**, pushed with an
immutable commit tag, committed back to the GitOps kustomization, and pulled from the Nebius
registry. ArgoCD reads the private manifests repo
using a **GitHub token sourced from MysteryBox** at boot; registry, artifact, and SMTP credentials
also originate in versioned MysteryBox payloads. Root-owned services use the VM identity to
reconcile allowlisted values into dedicated Kubernetes Secrets without placing credential values
in Git, OpenTofu state, images, command output, or application logs.

Network posture is deliberately narrow. The Nebius security group admits only inbound **SSH (22)**,
**HTTPS (443)**, and **HTTP (80)** for ACME/redirect; a host `ufw` firewall is defense-in-depth. The
k3s API (6443) and the ArgoCD UI are **not** public — operators manage the cluster over an **SSH
tunnel** (`ssh -L`). Only the tenant SaaS app is exposed, on 443 via Traefik. The app itself is
tenant-scoped: passwordless email verification issues opaque bearer sessions, and every job and
artifact derives its tenant from the verified email rather than a caller-controlled header. Users,
sessions, jobs, and artifact manifests persist in SQLite on the single-writer `saas-data` PVC so a
valid token issued before a restart stays valid after it; pending one-time codes and rate-limit
windows stay in process memory (short-lived by design, safe to lose on restart). Training artifacts
remain durable in S3. The active orchestration adapter submits
bounded allowlisted jobs through the Nebius SDK using the VM-managed renewable identity token.
The server-side catalog selects the runtime and compute shape per job spec: SB3 uses the isolated
SB3 image on the right-sized L40S shape, while the default `go1-mjx-demo` expands to the verified
100M-step MJX workload using the isolated MJX image on a single H100.

### Secrets in use

All credentials originate in versioned **MysteryBox** payloads and reach workloads either as
Kubernetes Secrets reconciled by root-owned units (using the VM identity) or as secret references
resolved by Nebius services at use time. Values never appear in Git, OpenTofu inputs, command
arguments, or logs; OpenTofu records only non-secret secret/version IDs.

| MysteryBox secret | Payload keys | Consumed by |
| --- | --- | --- |
| `sim2policy-saas-github-token` | GitHub token | ArgoCD repo access, fetched once at boot by cloud-init |
| `sim2policy-saas-registry-pull` | `token` | k3s `nebius-registry` dockerconfigjson imagePullSecret (username `iam`) for pulling the SaaS app image |
| artifact access-key secret (created by `nebius_iam_v2_access_key.artifacts`) | `secret` (paired with the non-secret `artifact_access_key_id`) | `saas-nebius` Kubernetes Secret (`AWS_SECRET_ACCESS_KEY` for the backend's S3 artifact reads) and injected into each training job as a MysteryBox env-secret |
| `sim2policy-saas-smtp` | seven `SAAS_SMTP_*` keys | `saas-smtp` Kubernetes Secret for Mailjet login-code delivery |
| `sim2policy-job-registry-creds` | `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` | Serverless AI jobs API at image-pull time, referenced by version ID in each job's `registry_credentials` (the jobs API requires this exact key shape; the single-key `token` pull secret is not accepted there) |

Kubernetes Secrets on the cluster: `saas-nebius` (the orchestration env contract — `NEBIUS_*`,
`AWS_*`, `SIM2POLICY_*`, including selector/version references, reconciled by
`saas-nebius-sync.service`), `saas-smtp` (reconciled from one pinned version by
`saas-smtp-sync.service`), and the `nebius-registry` imagePullSecret. The orchestrator itself holds
no long-lived key: the Nebius SDK authenticates with the **VM-managed renewable IAM token** mounted
read-only into the pod. Payload-viewer permits are scoped per secret to the `saas-server-access`
group; rotation means adding a new MysteryBox version, updating only the pinned version ID, and
rerunning the corresponding sync unit.

### Email authentication and delivery

The browser calls `POST /auth/request-code`; only the backend generates the six-digit code. The
backend stores a hash with a ten-minute expiry, then sends the plaintext code through authenticated
Mailjet SMTP over STARTTLS. The production Deployment explicitly selects `smtp` and requires the
non-optional `saas-smtp` Kubernetes Secret. That Secret is reconciled from one pinned MysteryBox
version containing exactly seven allowlisted `SAAS_SMTP_*` keys. Local and test processes may
select `mock`, but the production manifest and CI assertion reject mock delivery.

Provider acceptance is part of request success. Connection, timeout, TLS, authentication,
recipient, quota, or provider rejection failures delete the unusable pending code and return a
sanitized retryable `503`; abuse rate limiting still counts the request. Real-delivery logs contain
only result category and latency, never the recipient, code, SMTP response, API Key, or Secret Key.
The sender domain is authenticated with SPF, DKIM, and DMARC, while inbox placement and delivery
events remain the responsibility of Mailjet and recipient mail systems.

### Control-plane durability and rebuildability

Git remains canonical for manifests and immutable image selection, MysteryBox for credentials, S3
for training artifacts, and SQLite/PVC storage for transactional SaaS state. The PVC is node-local
and single-writer, matching the one-replica deployment; it improves rollout/restart durability but
is not a cross-node database or independent backup. Rebuilding the VM therefore also requires a
planned SQLite backup/restore or migration if that state must survive loss of the node/disk.

## Execution and safety model

Training, evaluation, rendering, and reporting are separate commands sharing one run identity.
Rendering tries EGL and retries once with OSMesa in a fresh process. Cloud acceptance proceeds from
cheap gates to expensive ones: image health/render smoke, bounded training plus storage sync,
interruption/resume, then full training and publication. Credentials stay in local configuration or
Nebius MysteryBox; generated artifacts and infrastructure state never belong in Git.

MJX training logs JAX backend/device discovery and explicit setup, initial-checkpoint,
compile/train, checkpoint-publication, and artifact-sync phases. A two-second `nvidia-smi` sampler
spans those phases and writes schema-v2 runtime telemetry with sample counts, mean/max utilization,
peak memory, and phase durations; start/end snapshots remain for compatibility but are not treated
as whole-run utilization.

Container images are built on CPU-only builders and consumed by separate ephemeral GPU AI Jobs.
This keeps Docker compilation and registry upload off costly accelerator time. SB3 jobs use L40S;
the flagship MJX job uses H100. The full Track
A flow uses `Go1JoystickFlatTerrain`, Brax PPO on MJX, immutable image digests, periodic S3
checkpoints, and a finalizer that downloads the durable run, restores progression checkpoints,
renders media, evaluates the final policy, writes reports/comparison data, and republishes the
completed manifest. See `sim2policy/docs/submission-checklist.md` for the verified run and artifact
references.
