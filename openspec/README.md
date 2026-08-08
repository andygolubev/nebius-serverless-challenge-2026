# OpenSpec

`specs/` is the behavioural contract for this repository: one directory per capability, each holding
a `spec.md` with a purpose, its requirements, and the scenarios that verify them. It answers *what
each capability must do*. [`../ARCHITECTURE.md`](../ARCHITECTURE.md) answers *how the system is put
together and why*, and its "Where things are documented" table points at the detailed operational
document for each area.

Specs describe the `main` branch as it actually behaves. If code and spec disagree, one of them is a
bug — say which, and fix it.

## Capabilities

**Data plane — the training template**

| Capability | Scope |
| --- | --- |
| `policy-training-backends` | Validated run configs, SB3 and MJX trainers, backend isolation, reproducibility metadata |
| `durable-run-artifacts` | Per-run layout, S3 sync, complete-before-publish checkpoints, resumption |
| `run-state-artifacts` | Object-storage run prefix, status lifecycle, artifact manifest |
| `rollout-media` | Deterministic rollouts, EGL/OSMesa fallback, render smoke, progression montage |
| `policy-evaluation-reporting` | Multi-seed evaluation, metrics schema, honest cost, checkpoint selection |
| `training-presets` | The declarative demo allowlist |
| `training-demo-api` | The stateless data-plane FastAPI surface |
| `training-job-orchestration` | Demo-API orchestration behind `mock` / `nebius` |
| `training-runtime-image-pipeline` | `sb3` / `mjx` image builds, immutable then compatibility tags |
| `serverless-template-workflow` | Clone-and-run: images, smoke gates, submission wrapper, Make targets |
| `showcase-run-curation` | The campaign workflow that produces curated runs |

**Control plane — infrastructure and delivery**

| Capability | Scope |
| --- | --- |
| `saas-control-plane-infra` | `saas-server` VM, k3s + ArgoCD bootstrap, minimal ingress, least-privilege IAM |
| `saas-orchestration-infrastructure` | Orchestrator identity, metadata-token auth, secret reconciliation |
| `gitops-delivery` | ArgoCD as the deployment mechanism, `main` as the source revision |
| `saas-image-pipeline` | SaaS image build, push, and GitOps tag bump |
| `saas-domain-tls` | Public domain, cert-manager, automatic Let's Encrypt issuance |
| `saas-data-persistence` | SQLite on the PVC, quotas, atomic reservations, retention |

**Product surfaces**

| Capability | Scope |
| --- | --- |
| `saas-email-auth` | Passwordless one-time-code login and bearer sessions |
| `saas-job-customization` | The single job-creating route and what is refused everywhere else |
| `saas-nebius-orchestration` | Typed submissions, durable reconciliation, artifact-gated completion |
| `saas-artifact-access` | Tenant-authorized and public artifact resolution and delivery |
| `saas-robot-assets` | Bounded MJCF upload, structural validation, immutable versions |
| `saas-environment-builder` | Server-owned tasks, scenes, and bounded objects |
| `custom-robot-training-preparation` | The bounded preparation gate and its fingerprint |
| `custom-robot-sb3-runtime` | The generic runtime, task contracts, and fixed training profile |
| `custom-robot-policy-bundle` | Custom-run bundle contents and load verification |
| `policy-bundle-export` | Common bundle envelope, determinism, and download surfaces |
| `public-training-showcase` | The read-only curated gallery |
| `saas-web-ui` | Design system, showcase, dashboard, My Robots, result views |
| `site-visit-analytics` | Privacy-preserving visit and page-view recording |
| `my-robots-validation-suite` | The exhaustive validation matrix and its cost gates |

## Working on a change

Active work goes under `changes/<change-id>/` (proposal, design, spec deltas, tasks) via the
OpenSpec skills. Historical changes were consolidated into `ARCHITECTURE.md` and the READMEs; their
full text remains in Git history.
