#!/usr/bin/env bash
set -euo pipefail

# Replaces the `validation` blocks that used to guard saas_sb3_image_tag and
# saas_mjx_image_tag at plan time. Now that Git owns the runtime job images, this
# is the pre-merge gate: the backend's startup check (settings.py) is the last
# line of defence, and a readiness failure is a worse place to learn about a typo.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
env_file="$repo_root/deploy/manifests/saas/runtime-images.env"
deployment="$repo_root/deploy/manifests/saas/deployment.yaml"
kustomization="$repo_root/deploy/manifests/saas/kustomization.yaml"

fail() {
  echo "saas runtime image check failed: $1" >&2
  exit 1
}

test -f "$env_file" || fail "$env_file is missing"

# The generator must stay hashed: the SaaS backend reads these at startup, so a
# value change has to roll the pods. disableNameSuffixHash would leave the old
# ReplicaSet running the old image with no signal that anything is stale.
grep -Fq "name: saas-runtime-images" "$kustomization" \
  || fail "kustomization.yaml must generate the saas-runtime-images ConfigMap"
if grep -Fq "disableNameSuffixHash: true" "$kustomization"; then
  fail "the runtime image ConfigMap must keep its name suffix hash so pods roll on change"
fi

expected_keys="CUSTOM_ROBOT_SB3_IMAGE SIM2POLICY_JOB_IMAGE SIM2POLICY_MJX_JOB_IMAGE"

for key in $expected_keys; do
  grep -Eq "^${key}=" "$env_file" || fail "$key is missing from runtime-images.env"

  # The Deployment must consume every key explicitly. An omitted entry silently
  # falls through to the stale copy in the saas-nebius secret.
  grep -Fq "key: $key" "$deployment" \
    || fail "deployment.yaml must read $key from the saas-runtime-images ConfigMap"
done

while IFS='=' read -r key value; do
  case "$key" in ''|\#*) continue ;; esac

  case "$value" in
    */sim2policy:*|*/sim2policy@sha256:*) ;;
    *) fail "$key must be a fully qualified sim2policy registry reference, got '$value'" ;;
  esac

  case "$key" in
    SIM2POLICY_MJX_JOB_IMAGE) prefix="mjx" ;;
    *) prefix="sb3" ;;
  esac

  if ! printf '%s' "$value" | grep -Eq "(@sha256:[0-9a-f]{64}|:${prefix}-[0-9a-f]{40})$"; then
    fail "$key must pin an immutable ${prefix}-<40-char git SHA> tag or a digest, got '$value'"
  fi
done <"$env_file"

# The gallery and uploaded-robot paths must run the same SB3 build; a split here
# is the exact drift the old two-file bump kept producing.
gallery="$(grep -E '^SIM2POLICY_JOB_IMAGE=' "$env_file" | cut -d= -f2-)"
custom="$(grep -E '^CUSTOM_ROBOT_SB3_IMAGE=' "$env_file" | cut -d= -f2-)"
if [ "$gallery" != "$custom" ]; then
  fail "SIM2POLICY_JOB_IMAGE and CUSTOM_ROBOT_SB3_IMAGE must reference the same SB3 build"
fi

# Nothing may reintroduce a hardcoded runtime image in the Deployment.
if grep -Eq 'value: .*/sim2policy:(sb3|mjx)-' "$deployment"; then
  fail "deployment.yaml must not hardcode a runtime image; use the ConfigMap reference"
fi

# --- Promotion workflow ---------------------------------------------------
# The bump job runs with repository write access, so its guards are load-bearing.
workflow="$repo_root/.github/workflows/training-runtime-images.yml"

require() {
  grep -Fq -- "$1" "$workflow" || fail "$2"
}

require "contents: write" "the runtime bump needs scoped repository write permission"
require "needs: build-validate-push" \
  "the bump must run once after both matrix legs so sb3 and mjx cannot race"
require "github.event_name == 'workflow_dispatch' && inputs.promote" \
  "promotion must be a deliberate dispatch, never an automatic main-push rollout"
require 'git merge-base --is-ancestor "$GITHUB_SHA" origin/main' \
  "the bump must refuse refs that are not merged to main"
require "attempt in 1 2 3" \
  "the bump must rebase and retry rather than drop a requested promotion"
require "bash deploy/tests/assert-saas-runtime-images.sh" \
  "the bump must revalidate the rewritten file before pushing"
require "[skip ci]" "bot promotion commits must prevent recursive CI"

echo "saas runtime image assertions passed"
