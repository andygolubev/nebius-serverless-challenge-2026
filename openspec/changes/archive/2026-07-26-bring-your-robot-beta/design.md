## Context

The tenant SaaS currently exposes only production-executable Go1 MJX profiles. Its catalog and
submission boundary intentionally reject arbitrary environments, images, commands, and code. The
requested Bring Your Robot experience must preserve that truthfulness while giving users a useful
way to check whether a custom robot description and proposed locomotion setup fit a supported
contract.

An MJCF file describes bodies, joints, actuators, and geometry; it does not supply a complete RL
environment, observation/action contract, reward, termination rule, evaluation criterion, or
accepted production job specification. Therefore this change ends at validated onboarding and
environment drafting. A later change can consume the normalized contract to build and accept a
generic MJX training adapter without weakening the executable-catalog invariant.

## Goals / Non-Goals

**Goals:**

- Provide a polished, tenant-scoped upload and validation workflow for small self-contained MJCF
  locomotion robots.
- Include two original, redistributable, primitive-only sample files (quadruped and biped) that
  pass exactly the same public validator as tenant uploads.
- Let users choose server-owned locomotion tasks and bounded scene objects instead of submitting
  environment or reward code.
- Persist immutable robot versions and normalized environment drafts across restarts.
- Make the distinction between structurally validated and production-trainable unmistakable in
  API responses and UI copy.

**Non-Goals:**

- Training an uploaded robot locally or on Nebius in this change.
- Modifying the Go1 production catalog, job specifications, orchestration adapter, or runtime
  image.
- ZIP bundles, meshes, textures, height fields, plugins, includes, custom object files, Python
  environments, reward functions, containers, sensors requiring executable adapters, or remote
  URLs.
- Physical/dynamic correctness guarantees, sim-to-real deployment, URDF/USD/SDF conversion, or a
  general 3D scene editor.
- Implementing the separate seven-example trainable gallery.

## Decisions

### Accept one self-contained primitive-only MJCF file

`POST /robots` uses multipart form data with `name`, `robot_type`, and one `.xml` file. The beta
accepts at most 1 MiB of UTF-8 XML and only `quadruped` or `biped` as declared robot types. The
validator rejects DTD/entity declarations before parsing; rejects includes, plugins, external
references, meshes, textures, height fields, and file/directory attributes; and permits only
primitive collision/visual geometry.

The normalized structure is limited to one floating robot root, 64 bodies, 64 joints, 64
actuators, 128 geoms, and XML depth 16. Every actuated joint must exist, names must be unique, and
the upload must contain at least one controllable hinge joint. Errors are field-oriented and never
echo raw XML.

This is preferred over ZIP/mesh support because a single XML has no archive traversal, missing
sidecar, mesh parser, licensing, or external-path ambiguity. It is preferred over accepting any
MJCF that MuJoCo can parse because compilation alone does not enforce this product's portability
or security boundary.

### Validation is structural, deterministic, and honestly labeled

A successful upload receives a SHA-256 digest, an immutable UUID version, parsed counts, actuator
and joint names, robot type, validation timestamp, and `readiness: validated`. It also returns
`trainable: false` with a stable reason code such as `custom-training-not-enabled`.

Re-uploading identical content for the same tenant and declared type returns the existing version
instead of creating duplicates. `validated` means the file satisfies the constrained data
contract; it does not claim stable dynamics or policy convergence.

This preserves the current rule that every trainable choice must resolve to an accepted job spec.

### Store bounded XML and drafts in SQLite on the existing PVC

The upload is small enough to store as UTF-8 text alongside metadata in new `robot_assets` and
`robot_setups` tables. Each row carries `tenant_id`; every lookup derives tenant identity from the
bearer session. Robot content is immutable. Deletion is a soft delete so existing drafts remain
internally consistent, while normal list/detail routes hide deleted assets.

This reuses the existing single-node durability model and transactional tenant isolation. A new
object-storage subsystem would add credentials and lifecycle complexity without helping a
validation-only 1 MiB beta.

### Ship two original sample robots through the same contract

`saas/samples/robots/` contains `sample-quadruped.xml`, `sample-biped.xml`, and a README describing
the upload constraints. The models use only boxes, spheres, cylinders, and capsules and contain no
third-party meshes or model-derived geometry. Authenticated sample endpoints list and download the
exact files; the backend validates them at startup/test time so samples cannot drift from the
public validator.

### Compose environments from small server-owned catalogs

The beta exposes three task templates:

- `stand-balance` for bipeds and quadrupeds.
- `walk-forward` for bipeds and quadrupeds.
- `recover-from-fall` for quadrupeds only.

It also exposes four scene presets (`flat-arena`, `ramp-course`, `hurdle-course`, and
`step-course`) built from a fixed primitive-object catalog (`box`, `ramp`, `hurdle`, and `step`). A
tenant may use a preset as-is or add at most six catalog objects. Object type, position, rotation,
and dimensions use server-declared numeric bounds; the server resolves defaults and persists a
normalized JSON draft.

This provides useful choice without custom object upload. File-backed objects are explicitly
deferred because even a simple mesh creates format parsing, units, collision geometry, complexity,
licensing, and storage questions that the beta does not need.

### Add a My Robots workflow without changing the job composer

The top navigation gains **My Robots**. The workspace lists sample downloads and tenant robots,
supports upload, displays validation diagnostics and parsed statistics, and opens an environment
builder with task and scene cards plus bounded object controls. Saved setups show a prominent
`Validated setup` badge and disabled `Training coming after GPU validation` action.

The existing New Job composer remains driven solely by `/training-options`; custom robots and
setups never appear there and cannot be submitted through `POST /jobs`.

## Risks / Trade-offs

- [Users may interpret XML validation as deployment readiness] → Use `validated`, `trainable:
  false`, a stable reason code, and repeated UI explanation; never show a Start Training action.
- [A valid MJCF may still be physically unusable] → Report structural scope explicitly and defer
  compile/dynamics/convergence claims to the future training-adapter change.
- [SQLite grows if many models are uploaded] → Enforce 1 MiB per model, tenant quotas (maximum 20
  active robot versions and 50 setups), and soft-deletion visibility rules.
- [XML parser abuse] → Bound bytes, nodes, depth, and counts; reject DTD/entities and all external
  references before parsing; test hostile inputs.
- [Object options feel limited] → Provide task-relevant presets and a bounded custom composition
  mode; expand only after acceptance data shows a specific missing primitive.
- [Future training requires a different storage path] → Keep digest and normalized contract stable
  so a later migration can copy immutable XML to object storage without changing tenant identity
  or setup semantics.

## Migration Plan

1. Add additive SQLite tables and stores; existing users, sessions, jobs, and artifacts remain
   unchanged.
2. Add validator, catalogs, samples, and tenant API routes with backend tests.
3. Add frontend types, My Robots navigation/workspace, builder, and accessibility tests.
4. Build and smoke-test the SaaS image with a persistent temporary database; upload both samples,
   save setups, restart, and verify tenant isolation and honest readiness.
5. Deploy through the existing image/GitOps flow only after local verification. No cloud training
   resources are created.

Rollback restores the earlier SaaS image. Additive tables and stored uploads remain inert and can
be retained or removed later without affecting jobs.

## Open Questions

None for this beta. Mesh/object upload and actual custom training are deliberate follow-on changes,
not unresolved implementation choices.
