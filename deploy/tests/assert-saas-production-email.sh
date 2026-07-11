#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
manifest="$repo_root/deploy/manifests/saas/deployment.yaml"

email_backend="$(awk '
  /- name: SAAS_EMAIL_BACKEND/ { found=1; next }
  found && /value:/ { print $2; exit }
' "$manifest")"
if [ "$email_backend" != "smtp" ]; then
  echo "production SaaS manifest must set SAAS_EMAIL_BACKEND=smtp" >&2
  exit 1
fi

if ! awk '
  /name: saas-smtp/ { found=1; next }
  found && /optional: false/ { valid=1; exit }
  found && /^[[:space:]]*[^[:space:]]/ { exit }
  END { exit !valid }
' "$manifest"; then
  echo "production SaaS manifest must reference non-optional saas-smtp" >&2
  exit 1
fi

echo "production email manifest assertion passed"
