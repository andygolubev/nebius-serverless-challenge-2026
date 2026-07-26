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
require "branches: [main, debug-portal]" \
  "workflow must build debug-portal changes"
require "github.event_name == 'push' && github.ref == 'refs/heads/debug-portal'" \
  "deployment bump must be restricted to debug-portal pushes"
require 'git rev-parse origin/debug-portal)" != "$GITHUB_SHA"' \
  "deployment bump must refuse stale debug-portal builds"
require "git push origin HEAD:debug-portal" \
  "deployment bump must update debug-portal only"
require "[skip ci]" "bot deployment commits must prevent recursive CI"
require "kustomize edit set image" "deployment must update the kustomization image"

echo "saas-image GitOps workflow assertions passed"
