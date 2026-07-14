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

When `gallery_enabled` is true, production exposes exactly seven accepted examples: `go1-walker`,
`ant-explorer`, `halfcheetah-sprint`, `hopper-balance`, `walker2d-stride`, `g1-rough-terrain`, and
`reacher-target`. The response contains the server-selected backend/hardware, measured guidance,
success rule, accepted revision, recommended profile, and bounded optional fields. Go1 Quick,
Standard, and Quality are sizes beneath the one Go1 card. Entries with a stale acceptance revision
are omitted and rejected.

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/training-options" | jq .
```

Accepted gallery examples can be listed with:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/training-options" | jq -r '.examples[] | [.id, .backend_label, .hardware_label, .recommended_profile] | @tsv'
```

For the deployed Nebius backend, only `total_timesteps` and `seed` are currently forwarded to the
training command. The catalog also validates `learning_rate`, but the cloud adapter intentionally
does not forward that three-level configuration override because the training config loader rejects
it. Check `JOB_SPECS` and each spec's `param_paths` in `backend/app/catalog.py` before assuming a new
parameter affects a cloud run.

## Submit a job

With the gallery enabled, use this form:

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"gallery_example_id":"hopper-balance","gallery_profile_id":"hopper-balance-v1","params":{"seed":7}}' \
  "$BASE_URL/jobs"
```

The legacy disabled-gallery rollout accepts exactly one of these forms:

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
      "preset": "go1-mjx-quick",
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
      "environment": "go1",
      "algorithm": "ppo-mjx",
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

## Validate, prepare, and train a custom robot setup

Custom models never enter the public catalog or generic `POST /jobs`. Eligible owned setups use
their setup-bound Prepare and Start endpoints; every image, command, CPU shape, timeout,
hyperparameter, secret selector, and S3 prefix remains server-owned.

List and download the canonical examples without printing the bearer token or model content:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/robot-samples" \
  -H "Authorization: Bearer $TOKEN" | jq .

curl --fail-with-body --silent --show-error \
  "$BASE_URL/robot-samples/sample-quadruped" \
  -H "Authorization: Bearer $TOKEN" \
  --output /tmp/sample-quadruped.xml
```

Upload one bounded XML file with a declared type:

```bash
robot_response="$(curl --fail-with-body --silent --show-error \
  -X POST "$BASE_URL/robots" \
  -H "Authorization: Bearer $TOKEN" \
  -F 'name=Quadruped API check' \
  -F 'robot_type=quadruped' \
  -F 'file=@/tmp/sample-quadruped.xml;type=application/xml')"
printf '%s\n' "$robot_response" | jq .
ROBOT_ID="$(printf '%s' "$robot_response" | jq -er '.id')"
```

The upload response says `readiness: validated`, `trainable: false`, and
`reason: custom-training-not-enabled`; training readiness belongs to a saved setup, not the XML.
Capture the opaque `.id` only if continuing the setup test;
do not log private XML or bearer values. Discover the server-owned task/scene/object choices and
bounds before composing a draft:

```bash
curl --fail-with-body --silent --show-error \
  "$BASE_URL/environment-catalog" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

`POST /robot-setups` accepts JSON containing `name`, an owned `robot_id`, a compatible
`task_template_id`, a `scene_preset_id`, and up to six total bounded catalog objects. It does not
accept file, URL, mesh, environment code, or task code fields. Robot and setup list/detail/content/
delete routes are tenant scoped and return 404 for another tenant. Deletion is soft; do not use it
during retained production acceptance when the user wants to inspect the same rows afterward.

Only biped/quadruped × Stand Balance/Walk Forward × Flat Arena/Ramp Course with no optional objects
is trainable in V1. Save the returned setup ID without printing tenant XML:

```bash
setup_response="$(curl --fail-with-body --silent --show-error \
  -X POST "$BASE_URL/robot-setups" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data "{\"name\":\"Quadruped walk\",\"robot_id\":\"$ROBOT_ID\",\"task_template_id\":\"walk-forward\",\"scene_preset_id\":\"flat-arena\",\"objects\":[]}")"
SETUP_ID="$(printf '%s' "$setup_response" | jq -er '.id')"
prepare_response="$(curl --fail-with-body --silent --show-error \
  -X POST "$BASE_URL/robot-setups/$SETUP_ID/preparations" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{}')"
printf '%s\n' "$prepare_response" | jq '{id,state,phase,fingerprint}'
```

Poll the owner-scoped latest endpoint until `accepted` or `failed`; only bounded phase/reason data
is public:

```bash
while true; do
  preparation="$(curl --fail-with-body --silent --show-error \
    "$BASE_URL/robot-setups/$SETUP_ID/preparations/latest" \
    -H "Authorization: Bearer $TOKEN")"
  state="$(printf '%s' "$preparation" | jq -r '.state')"
  printf 'state=%s phase=%s reason=%s\n' "$state" \
    "$(printf '%s' "$preparation" | jq -r '.phase')" \
    "$(printf '%s' "$preparation" | jq -r '.failure_reason // "-"')"
  case "$state" in accepted|failed) break ;; esac
  sleep 10
done
```

A failed preparation is retried as a new attempt with `{"retry":true}`. For an accepted current
fingerprint, start one fixed job with a locally generated opaque idempotency key; do not put a token
or storage key in it:

```bash
IDEMPOTENCY_KEY="start-$(date -u +%Y%m%dT%H%M%SZ)-$(openssl rand -hex 8)"
job_response="$(curl --fail-with-body --silent --show-error \
  -X POST "$BASE_URL/robot-setups/$SETUP_ID/training-jobs" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  --data "{\"idempotency_key\":\"$IDEMPOTENCY_KEY\"}")"
JOB_ID="$(printf '%s' "$job_response" | jq -er '.id')"
printf '%s\n' "$job_response" | jq '{id,job_kind,status,preparation_fingerprint,resolved_config}'
unset IDEMPOTENCY_KEY
```

The result lifecycle and artifact endpoints below are identical to normal Jobs. A custom policy
bundle contains the exact simulator contract and is explicitly not directly deployable to a
physical robot. Keep the SaaS Job row and S3 artifacts during acceptance; delete neither the setup
nor job evidence the user needs to inspect.

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

The full tenant lifecycle is
`queued → starting → training → finalizing → rendering → evaluating → completed`, or `failed` from
any phase. `nebius_job_id` appears after remote creation succeeds and can be inspected with the
Nebius CLI when operator cloud access is available:

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
