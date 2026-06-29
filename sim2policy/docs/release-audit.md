# Release audit

Run from the repository root before submission.

## Secret audit

```bash
git grep -n -E 'AKIA|ASIA|aws_secret_access_key|PRIVATE KEY|BEGIN .*KEY|password|token|secret' -- . ':!sim2policy/uv.lock'
find . -name '.env*' -o -name 'credentials.json' -o -name 'service-account*.json'
```

Expected state: no committed cloud credentials, no private keys, no local environment files, and no
raw secret selectors in generated metadata.

## Large-file audit

```bash
find . -type f -size +5M \
  -not -path './.git/*' \
  -not -path './sim2policy/.venv/*' \
  -not -path './sim2policy/uv.lock' \
  -print
git status --ignored --short sim2policy/runs sim2policy/assets
```

Expected state: no committed checkpoints, TensorBoard logs, full videos, or generated run
directories. Lightweight assets under `sim2policy/assets/samples/` are allowed.

## Clean quickstart rehearsal

```bash
cd sim2policy
uv sync --extra dev
uv run ruff check src tests
uv run mypy src
uv run pytest
uv run sim2policy validate-config configs/smoke_sb3.yaml
DRY_RUN=1 IMAGE=example/sim2policy:sb3 CONFIG=configs/smoke_sb3.yaml RUN_ID=audit PLATFORM=gpu-l40s-d PRESET=1gpu-16vcpu-200gb TIMEOUT=1h SUBNET_ID=subnet jobs/submit.sh
```

Linux/NVIDIA rehearsal additionally runs:

```bash
uv sync --extra dev --extra sb3
uv run python -m sim2policy.health --backend sb3
uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --output runs/audit/videos/random.mp4 --smoke-test
```
