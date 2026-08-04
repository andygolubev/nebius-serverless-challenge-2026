#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
workflow="$repo_root/.github/workflows/saas-image.yml"

require() {
  local pattern="$1"
  local message="$2"
  if ! grep -Fq -- "$pattern" "$workflow"; then
    echo "saas-image workflow check failed: $message" >&2
    exit 1
  fi
}

require "contents: write" "GitOps bump needs scoped repository write permission"
require "branches: [main]" \
  "workflow must build main changes"
require "github.event_name == 'push' && github.ref == 'refs/heads/main'" \
  "deployment bump must be restricted to main pushes"
require 'git rev-parse origin/main)" != "$GITHUB_SHA"' \
  "deployment bump must refuse stale main builds"
require "git push origin HEAD:main" \
  "deployment bump must update main only"
require "[skip ci]" "bot deployment commits must prevent recursive CI"
require "kustomize edit set image" "deployment must update the kustomization image"

echo "saas-image GitOps workflow assertions passed"
