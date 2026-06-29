# Nebius job operation

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

