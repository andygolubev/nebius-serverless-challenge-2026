## 1. Cloud IAM & Secrets (manual/CLI, documented)

- [x] 1.1 Create a dedicated backend service account (e.g. `sim2policy-saas-orchestrator`) and grant it `editor` on the project; document why `editor` is required (no job-scoped role) and record the account in `sim2policy/infra/nebius/README.md`
- [x] 1.2 Store the backend SA credentials in MysteryBox; confirm the existing `sim2policy-artifacts` S3 access key/secret are available via a MysteryBox selector *(evolved: the orchestrator uses the VM-managed IAM token file — no long-lived SA key exists anywhere; the artifact S3 secret is confirmed available via its MysteryBox selector `mbsec-…/mbsecver-…`)*
- [x] 1.3 Document (not commit) the procedure to create the `saas-nebius` Kubernetes Secret from MysteryBox values (SA key + AWS creds + endpoint/region/bucket)

## 2. Backend dependencies & configuration

- [x] 2.1 Add `nebius` and `boto3` to `saas/backend/requirements.txt` (pinned)
- [x] 2.2 Add a settings module/loader for the `nebius` backend env contract: `NEBIUS_PROJECT_ID`, `NEBIUS_SUBNET_ID`, `SIM2POLICY_JOB_IMAGE`, registry/MysteryBox secret identifiers, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_DEFAULT_REGION`, `SIM2POLICY_S3_BUCKET`; validate and fail fast in `build_backend("nebius")`
- [x] 2.3 Extend the preset catalog beside `ALLOWED_PRESETS` with per-preset job parameters (training module, config, platform, preset size, timeout, step caps) mirroring `sim2policy/jobs/submit.sh` defaults

## 3. Nebius orchestration backend

- [x] 3.1 Add `nebius_job_id: str | None` to the `Job` model and persist it through `JobStore`
- [x] 3.2 Implement `NebiusBackend.launch()`: validate run ID against `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`, build `CreateJobRequest` from the preset catalog only (name `sim2policy-<run-id>`, container command/args, platform/preset, timeout, subnet, restart-policy never, registry secret), inject `AWS_ACCESS_KEY_ID` as env and `AWS_SECRET_ACCESS_KEY` as MysteryBox env-secret, call `JobServiceClient.create()`, and store the returned `aijob-*` ID
- [x] 3.3 Implement submission failure handling: mark job `failed` with a sanitized error summary (no secrets/stack traces)
- [x] 3.4 Implement the per-job poller thread: call `JobService.get()` on an interval, map Nebius states → tenant lifecycle in a single tested function, stop on terminal state, and enforce a timeout margin that marks stuck jobs `failed`
- [x] 3.5 Register `nebius` in `build_backend()`; keep `mock` as default

## 4. S3 artifact access

- [x] 4.1 Implement an S3 artifact reader (`boto3` client against `AWS_ENDPOINT_URL_S3`) that lists/reads `sim2policy/<run-id>/` and builds `ArtifactManifest` (status, metrics, media keys)
- [x] 4.2 Wire the reader into job completion: on Nebius success, populate artifacts from S3; keep the `409 artifacts not ready` behavior when the manifest is absent
- [x] 4.3 Unit-test the manifest builder against fixture object listings (no live S3)

## 5. Deploy manifests

- [x] 5.1 Update `deploy/manifests/saas/deployment.yaml` to source the S3 and Nebius env vars from the `saas-nebius` Secret (`secretKeyRef`/`envFrom`); keep the secret itself out of Git
- [x] 5.2 Switch `SAAS_ORCHESTRATION_BACKEND` to `nebius` in the deployed configuration (overlay or patch), leaving local/dev on `mock`

## 6. Verification

- [x] 6.1 Unit tests: backend selection, preset-only submission building, run-ID validation, state mapping, launch-failure path (SDK mocked)
- [x] 6.2 Confirm exact pysdk request/enum names against the installed SDK version and adjust the state-mapping function (design open question)
- [ ] 6.3 End-to-end smoke test in the cluster: submit `halfcheetah-demo`, watch lifecycle to `completed`, fetch real artifacts from `s3://sim2policy-artifacts/sim2policy/<run-id>/`; verify no secret values appear in logs or `kubectl describe`
