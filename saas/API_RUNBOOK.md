# SaaS UI API operator runbook

Use this runbook to submit and inspect tenant jobs through the public SaaS API. These calls exercise
the same authenticated API used by the web UI; they do not bypass tenant validation or the selected
orchestration backend.

## Token handling

The bearer token is an opaque tenant session returned by `POST /auth/verify`. Treat it as a secret:

- Never put a real token in Git, documentation, issue text, `IMPLEMENTATION_LOG.MD`, or a committed
  script.
- Avoid passing it as a literal shell argument because shell history and process inspection may
  retain it.
- Do not call `/auth/logout` when the user says the development session must remain active.
- A token can access only jobs owned by the verified email that created the session.

Set the endpoint and read a token without echoing it or putting its value in shell history:

```bash
BASE_URL=https://sim-policy-trainer-challenge.info
printf 'Bearer token: '
IFS= read -r -s TOKEN
printf '\n'
TOKEN="${TOKEN#Bearer }"  # Accept either the opaque token or a copied "Bearer …" value.
```

Confirm the session before creating a paid job:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/me" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Unset `TOKEN` when the operational session is finished. This only removes the local shell value; it
does not revoke the server-side session:

```bash
unset TOKEN
```

## Discover valid options

Do not copy stale parameter bounds from old runs. The unauthenticated catalog endpoint is the source
of truth for environments, compatible algorithms, presets, defaults, and validation ranges:

Production exposes three GPU-accelerated Go1 MJX/JAX PPO profiles: Quick, Standard, and Quality.
SB3 and combinations without an executable H100 job specification are intentionally absent and
rejected by direct API submission.

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/training-options" | jq .
```

Current preset names can be listed with:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/training-options" | jq -r '.presets[] | [.id, .environment, .algorithm, (.params | tostring)] | @tsv'
```

For the deployed Nebius backend, only `total_timesteps` and `seed` are currently forwarded to the
training command. The catalog also validates `learning_rate`, but the cloud adapter intentionally
does not forward that three-level configuration override because the training config loader rejects
it. Check `JOB_SPECS` and each spec's `param_paths` in `backend/app/catalog.py` before assuming a new
parameter affects a cloud run.

## Submit a job

Every request must use exactly one of these forms:

1. A preset, optionally overridden with bounded `params`.
2. An explicit compatible `environment` and `algorithm` with bounded `params`.

No request can supply an image, command, arbitrary environment variable, secret, or custom code.

### Preset with parameter overrides

```bash
response="$(curl --fail-with-body --silent --show-error \
    -X POST "$BASE_URL/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data '{
      "preset": "halfcheetah-demo",
      "params": {
        "total_timesteps": 200000,
        "seed": 7
      }
    }')"

printf '%s\n' "$response" | jq .
JOB_ID="$(printf '%s' "$response" | jq -er '.id')"
```

Preset parameters are merged over the preset defaults. A top-level `seed` is retained as a legacy
alias, but new automation should put `seed` inside `params` with the other overrides.

### Explicit environment and algorithm

```bash
response="$(curl --fail-with-body --silent --show-error \
    -X POST "$BASE_URL/jobs" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data '{
      "environment": "ant",
      "algorithm": "ppo-sb3",
      "params": {
        "total_timesteps": 250000,
        "seed": 42
      }
    }')"

printf '%s\n' "$response" | jq .
JOB_ID="$(printf '%s' "$response" | jq -er '.id')"
```

Always inspect `resolved_config` in the response. It is the server-validated configuration after
preset expansion and default merging.

## Follow lifecycle and remote job identity

Fetch one job:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/jobs/$JOB_ID" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Poll until the tenant job reaches a terminal state:

```bash
while true; do
  job="$(curl --fail-with-body --silent --show-error \
      "$BASE_URL/jobs/$JOB_ID" \
      -H "Authorization: Bearer $TOKEN")"
  status="$(printf '%s' "$job" | jq -r '.status')"
  printf '%s  status=%s  nebius_job_id=%s  error=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "$status" \
    "$(printf '%s' "$job" | jq -r '.nebius_job_id // "-"')" \
    "$(printf '%s' "$job" | jq -r '.error // "-"')"
  case "$status" in
    completed|failed) break ;;
  esac
  sleep 15
done
```

The tenant lifecycle is `queued → starting → training → completed` or `failed`. Some workloads may
also report `evaluating` or `rendering`. `nebius_job_id` appears after remote creation succeeds and
can be inspected with the Nebius CLI when operator cloud access is available:

```bash
NEBIUS_JOB_ID="$(printf '%s' "$job" | jq -er '.nebius_job_id')"
nebius ai job get --id "$NEBIUS_JOB_ID" --format json | jq '.status'
```

## Results and artifacts

Request the tenant artifact manifest:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/jobs/$JOB_ID/artifacts" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

The response contains opaque artifact identifiers and tenant-authorized application URLs, not raw
S3 keys. MP4 URLs redirect to short-lived object-storage URLs suitable for browser byte-range
playback; callers cannot request arbitrary bucket keys.

Remote training success enters `finalizing`; a job becomes `completed` only after its required
manifest, metrics, and media validate. A terminal failure includes sanitized `error` and
`failure_phase` fields. Preserve the SaaS job ID and remote `nebius_job_id` for diagnosis, but never
copy a bearer token or raw provider response into a log.

## Common responses

| HTTP status | Meaning | Safe action |
| --- | --- | --- |
| `201` | Job accepted | Save `.id`; poll the job resource. |
| `401` | Token absent, expired, or revoked | Obtain a new UI session; do not retry with a logged token. |
| `404` | Job missing or owned by another tenant | Check the job ID and the token's `/me` identity. |
| `409` | Artifact manifest not published | Check job status and the S3/finalization state. |
| `422` | Invalid preset, compatibility, type, bound, or parameter | Read the structured `detail`, then refresh `/training-options`. |
| `429` | Login-code request rate limited | Wait for the response window; do not loop requests. |

For a failed job, preserve the SaaS job ID, `nebius_job_id`, timestamps, sanitized `.error`, and
Nebius status for diagnosis. Never copy bearer tokens, AWS secret values, registry credentials, or
MysteryBox payloads into the handoff log.
