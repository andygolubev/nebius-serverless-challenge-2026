# Tasks: SaaS artifact lazy recovery

## 1. Backend code

- [x] 1.1 Expose the artifact reader: give `NebiusBackend` an `artifact_reader` attribute set in `build_backend("nebius")`; `MockBackend.artifact_reader = None` (saas/backend/app/orchestration.py)
- [x] 1.2 Add lazy fallback in `get_artifacts` (saas/backend/app/main.py): on store miss, if the job status is `completed` and the backend has a reader, call `read_manifest(job_id, job_id)`; on success `store.set_artifacts()` and return; on `None` or exception, log a warning and keep the 409

## 2. Tests

- [x] 2.1 Unit test: completed job, no cached manifest, stub reader returns a manifest → 200 and the manifest is cached (second call served from store without the reader)
- [x] 2.2 Unit test: completed job, reader returns `None` or raises → 409, no 5xx
- [x] 2.3 Unit test: non-completed job never triggers the reader; mock backend behavior unchanged
- [x] 2.4 Run the full `saas/backend` pytest suite

## 3. Deploy

- [ ] 3.1 Build and push the SaaS image; roll out via the existing GitOps flow (watch the ArgoCD `kustomize.images` override; live `saas` app may pin the image tag)
- [ ] 3.2 Verify in prod: `GET /jobs/{id}/artifacts` still 409s for a manifest-less run (pre-finalize)

## 4. Finalize run 9b32bd6038ec4c34a1ec4681f661bc84 (operational)

- [ ] 4.1 Submit a Nebius Serverless AI job on `gpu-l40s-a` / `1gpu-8vcpu-32gb` with the MJX image: `python -m sim2policy.finalize --config configs/go1_mjx.yaml --run-id 9b32bd6038ec4c34a1ec4681f661bc84` plus the standard `storage.mode=s3`, `storage.bucket`, `storage.endpoint_url`, `storage.region` overrides and MysteryBox `AWS_SECRET_ACCESS_KEY` wiring; timeout ~1h
- [ ] 4.2 Confirm `report/artifacts.json`, `report/metrics.json`, videos, and `checkpoints/final.zip` exist under the run prefix in S3
- [ ] 4.3 End-to-end: `curl $BASE/jobs/9b32bd6038ec4c34a1ec4681f661bc84/artifacts` with a tenant token returns 200 with metrics and media keys
- [ ] 4.4 Delete the completed finalize job from Nebius (cost hygiene)
