#!/usr/bin/env bash
set -euo pipefail

required=(IMAGE CONFIG RUN_ID PLATFORM PRESET TIMEOUT SUBNET_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then echo "missing required variable: $name" >&2; exit 2; fi
done
BACKEND="${BACKEND:-sb3}"
if [[ "$BACKEND" != sb3 && "$BACKEND" != mjx ]]; then echo "BACKEND must be sb3 or mjx" >&2; exit 2; fi
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
  echo "RUN_ID contains unsafe characters" >&2; exit 2
fi
if [[ ! "$TIMEOUT" =~ ^[0-9]+(h|m|s)([0-9]+(m|s))?$ ]]; then
  echo "TIMEOUT must be a Nebius duration such as 1h or 2h30m" >&2; exit 2
fi
module="sim2policy.train_${BACKEND}"
container_args=(-m "$module" --config "$CONFIG" --run-id "$RUN_ID")
if [[ -n "${S3_BUCKET:-}" ]]; then
  container_args+=(--set "storage.mode=s3" --set "storage.bucket=$S3_BUCKET")
fi
if [[ -n "${S3_ENDPOINT:-}" ]]; then
  container_args+=(--set "storage.endpoint_url=$S3_ENDPOINT")
fi
if [[ -n "${S3_REGION:-}" ]]; then
  container_args+=(--set "storage.region=$S3_REGION")
fi
printf -v container_args_string '%q ' "${container_args[@]}"
container_args_string="${container_args_string% }"
command=(nebius ai job create
  --name "sim2policy-${RUN_ID}"
  --image "$IMAGE"
  --container-command python
  --args "$container_args_string"
  --platform "$PLATFORM"
  --preset "$PRESET"
  --timeout "$TIMEOUT"
  --subnet-id "$SUBNET_ID"
  --restart-policy never)
if [[ -n "${PARENT_ID:-}" ]]; then command+=(--parent-id "$PARENT_ID"); fi
if [[ -n "${REGISTRY_SECRET:-}" ]]; then command+=(--registry-secret "$REGISTRY_SECRET"); fi
if [[ -n "${S3_SECRET:-}" ]]; then
  command+=(--env-secret "AWS_ACCESS_KEY_ID=${S3_SECRET}")
  command+=(--env-secret "AWS_SECRET_ACCESS_KEY=${S3_SECRET}")
fi
if [[ "${PREEMPTIBLE:-0}" == 1 ]]; then command+=(--preemptible); fi
if [[ "${DRY_RUN:-0}" == 1 ]]; then
  printf '%q ' "${command[@]}" | sed -E 's/(env-secret [^ ]+=)[^ ]+/\1<redacted>/g'
  printf '\n'
else
  "${command[@]}"
fi
