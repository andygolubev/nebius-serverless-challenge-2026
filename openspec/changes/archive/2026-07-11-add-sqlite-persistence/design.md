# add-sqlite-persistence — Design

## Context

The SaaS backend (`saas/backend/app/store.py`) holds all tenant state in two in-process stores:
`AuthStore` (users, sessions, pending codes, rate-limit windows) and `JobStore` (jobs, artifact
manifests). The deployment is a single replica reconciled by ArgoCD; every image rollout replaces
the pod and wipes all state. The store classes already sit behind narrow interfaces, and
`store.py`'s own docstring anticipates swapping the internals for durable storage.

Constraints:

- Single-replica k3s cluster on one Nebius VM; no external database service available or desired
  for the PoC.
- GitOps delivery: any new Kubernetes objects (PVC, volume mounts) must live in
  `deploy/manifests/saas/` and be synced by ArgoCD.
- Tests run the stores in-process with no cluster.

## Goals / Non-Goals

**Goals:**

- Users, sessions, jobs, and artifact manifests survive pod restarts and redeploys.
- No new Python dependencies (stdlib `sqlite3`) and no new services in the cluster.
- Store public interfaces unchanged — `main.py`, `auth.py`, and orchestration code keep working
  as-is.

**Non-Goals:**

- Multi-replica support or concurrent writers (SQLite + RWO PVC is deliberately single-writer,
  matching the existing single-replica assumption).
- Migrating job/run artifacts to the durable S3 run tree (separate capability, already specced).
- Schema migration tooling; `CREATE TABLE IF NOT EXISTS` at startup is sufficient for the PoC.

## Decisions

### SQLite via stdlib `sqlite3`, not Postgres or an ORM

A Postgres pod (or managed DB) adds an operator/manifests, credentials through the secret
pipeline, and connection handling — none of which the PoC needs at one replica. SQLAlchemy would
ease a later Postgres move but adds a dependency for four small tables; the store interfaces are
already the portability seam, so raw `sqlite3` behind them is enough.

### Persist users, sessions, jobs, artifacts — keep codes and rate limits in memory

Pending one-time codes live 10 minutes and rate-limit windows 15; losing them on restart is
harmless (the user re-requests a code). Keeping them in memory avoids writing security-sensitive
hashes to disk and keeps the hot verification path simple. Sessions and users are the state whose
loss actually hurts (forced logout on every deploy), and jobs/artifacts give returning users their
history.

### One database file, WAL mode, a connection per store guarded by the existing locks

A single file at `SAAS_DB_PATH` (default `saas.db` under a configurable data dir;
`:memory:`-style temp path for tests). WAL journal mode with `synchronous=NORMAL` for sane
durability/latency at this scale. The stores already serialize access with `threading.Lock`;
reusing that with `check_same_thread=False` avoids a connection-pool abstraction.

### PVC + `Recreate` strategy in the existing Deployment

A `PersistentVolumeClaim` (k3s `local-path` default StorageClass, 1Gi) mounted at `/data`, with
`SAAS_DB_PATH=/data/saas.db`. The Deployment strategy changes from rolling update to `Recreate` so
the old pod releases the ReadWriteOnce volume before the new pod schedules — otherwise rollouts
deadlock on the volume attach.

## Risks / Trade-offs

- [`Recreate` strategy introduces brief downtime on each rollout] → Acceptable for a PoC demo;
  seconds of downtime versus a wedged rollout with RWO.
- [`local-path` PV is bound to the single node] → The cluster is one node by design; if the VM is
  recreated by Terraform the data is gone, same blast radius as today plus everything else on the
  node.
- [SQLite writes on every request add latency] → Traffic is demo-scale; WAL mode keeps writes in
  the sub-millisecond range.
- [Schema drift on future changes with no migration tool] → Tables are tiny; additive `ALTER
  TABLE` statements at startup cover the foreseeable cases, and the PoC can afford a wipe if not.

## Migration Plan

None. This is a dev server with no data worth preserving: code and manifests land together in one
change, the pod starts fresh against an empty database, and rollback is simply reverting the
change (the PVC can be deleted independently).

## Open Questions

None — sizing (1Gi) and placement (`/data`) are low-stakes and easy to change later.
