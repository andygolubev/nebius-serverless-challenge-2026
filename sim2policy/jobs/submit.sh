#!/usr/bin/env bash
set -euo pipefail

required=(IMAGE CONFIG RUN_ID PLATFORM PRESET TIMEOUT SUBNET_ID)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then echo "missing required variable: $name" >&2; exit 2; fi
done
BACKEND="${BACKEND:-sb3}"
if [[ "$BACKEND" != sb3 && "$BACKEND" != mjx ]]; then echo "BACKEND must be sb3 or mjx" >&2; exit 2; fi
module="sim2policy.train_${BACKEND}"
command=(nebius ai job create
  --name "sim2policy-${RUN_ID}"
  --image "$IMAGE"
  --container-command python
  --args "-m $module --config $CONFIG --run-id $RUN_ID"
  --platform "$PLATFORM"
  --preset "$PRESET"
  --timeout "$TIMEOUT"
  --subnet-id "$SUBNET_ID"
  --restart-policy on-failure)
if [[ -n "${PARENT_ID:-}" ]]; then command+=(--parent-id "$PARENT_ID"); fi
if [[ -n "${REGISTRY_SECRET:-}" ]]; then command+=(--registry-secret "$REGISTRY_SECRET"); fi
if [[ -n "${S3_BUCKET:-}" ]]; then command+=(--env "SIM2POLICY_S3_BUCKET=$S3_BUCKET"); fi
if [[ -n "${S3_ENDPOINT:-}" ]]; then command+=(--env "SIM2POLICY_S3_ENDPOINT=$S3_ENDPOINT"); fi
if [[ -n "${S3_SECRET:-}" ]]; then
  command+=(--env-secret "AWS_ACCESS_KEY_ID=${S3_SECRET}:AWS_ACCESS_KEY_ID")
  command+=(--env-secret "AWS_SECRET_ACCESS_KEY=${S3_SECRET}:AWS_SECRET_ACCESS_KEY")
fi
if [[ "${DRY_RUN:-0}" == 1 ]]; then
  printf '%q ' "${command[@]}" | sed -E 's/(env-secret [^ ]+=)[^ ]+/\1<redacted>/g'
  printf '\n'
else
  "${command[@]}"
fi

