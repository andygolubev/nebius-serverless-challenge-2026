# Nebius job operation

Verified on 2026-06-29 against Nebius CLI `0.12.216`, its live command help, and the official
[Serverless AI jobs quickstart](https://docs.nebius.com/serverless/quickstart/jobs). The current
interface supports `--env`, `--env-secret`, `--platform`, `--preset`, `--subnet-id`, and a mandatory
1–168 hour timeout. `gpu-l40s-a` with `1gpu-8vcpu-32gb` is the smallest documented L40S preset;
`gpu-l40s-d` starts at `1gpu-16vcpu-96gb`.

The wrapper targets the current `nebius ai job create` interface. It requires `IMAGE`, `CONFIG`,
`RUN_ID`, `PLATFORM`, `PRESET`, `TIMEOUT`, and `SUBNET_ID`. Use `DRY_RUN=1` first; secret selectors
are accepted through `REGISTRY_SECRET` and `S3_SECRET` and redacted from previews.

Run gates in order: official NVIDIA visibility quickstart, Sim2Policy image health command, render
smoke, ten-minute training/storage sync, resume drill, then a full run. Check tenant GPU quotas and
admin-group membership before submitting. Debug jobs should use the one-hour platform minimum and
be cancelled as soon as their gate passes. Inspect jobs with `nebius ai job list` and the relevant
`get`/logs commands from your installed CLI. Durable outputs live under
`s3://<bucket>/sim2policy/<run-id>/`; cancelling a job does not delete them.

Never pass raw registry or S3 credentials on the command line. Put them in MysteryBox and supply
selectors to the wrapper.

Infrastructure is managed in `infra/nebius` using OpenTofu 1.12.3 and Nebius provider 0.6.22.
Use `tofu output -raw sb3_image`, `artifact_bucket`, and `artifact_secret_selector` rather than
copying resource identifiers into source files. The wrapper maps the bucket, endpoint, and region
to validated config overrides and passes one MysteryBox selector to both standard AWS credential
environment variables.

The official visibility gate completed on 2026-06-29 as job `aijob-e00sescyvnw0qat56h` using
`gpu-l40s-a`, `1gpu-8vcpu-32gb`, subnet `vpcsubnet-e00ka7ggch340z2eyj`, and a one-hour safety
timeout. The workload itself ran for less than one second and reported NVIDIA L40S, 46,068 MiB,
driver 580.159.04, and CUDA 13.1.
