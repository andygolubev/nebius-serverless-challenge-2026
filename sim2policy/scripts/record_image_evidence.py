"""Record immutable-image evidence for the campaign gate (task 7.5).

Turns three separate facts into the one document `implementation-gate` and
`preflight` consume:

* the digest the **registry** serves for the immutable tag, which is what a job
  will actually pull — not what the builder happens to have cached locally;
* the digest the **local** image reports, compared against it, because a mismatch
  means the tag was re-pushed and the reviewed artifact is gone;
* the in-image audit from `audit_image_contents.py`, proving the planned configs
  and modules are present and that no credential or generated training artifact
  was baked into a layer.

Written through `CampaignStore`, so the document is redacted and atomically
replaced like every other piece of campaign state. Runs only on an approved Nebius
resource: the whole point of the record is where it was produced.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from sim2policy.campaign_redaction import sanitize_exception
from sim2policy.campaign_state import CampaignStore, utc_now
from sim2policy.execution_location import require_nebius_execution, write_location_attestation

TIMEOUT_SECONDS = 300


def _run(command: list[str], *, timeout: int = TIMEOUT_SECONDS) -> tuple[int, str, str]:
    completed = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


#: The registry accumulates one manifest per pushed revision, so the default page
#: is quickly too small. A freshly pushed tag falling off the first page reads as
#: "not present" and silently blocks the gate, so ask for the whole listing.
_REGISTRY_PAGE_SIZE = "1000"


def _registry_digest(registry_id: str, tag: str) -> tuple[str | None, str]:
    """Ask the registry which manifest the immutable tag currently resolves to."""
    code, stdout, stderr = _run(
        [
            "nebius",
            "registry",
            "image",
            "list",
            "--parent-id",
            registry_id,
            "--page-size",
            _REGISTRY_PAGE_SIZE,
            "--format",
            "json",
        ]
    )
    if code != 0:
        return None, f"registry list failed (exit {code}): {stderr.strip()[:200]}"
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return None, sanitize_exception(exc)
    for item in payload.get("items", []):
        if not isinstance(item, dict) or item.get("type") != "MANIFEST":
            continue
        if tag in (item.get("tags") or []):
            return str(item.get("digest")), "nebius-registry"
    return None, f"tag {tag} is not present in the registry"


def _local_digest(reference: str) -> str | None:
    code, stdout, _stderr = _run(
        ["sudo", "docker", "image", "inspect", reference, "--format", "{{json .RepoDigests}}"]
    )
    if code != 0:
        return None
    try:
        digests = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    for entry in digests:
        _repository, _, digest = str(entry).partition("@")
        if digest:
            return digest
    return None


def _image_audit(reference: str, runtime: str, script: Path) -> dict[str, Any]:
    """Run the content audit inside the image, with no network and no writes."""
    code, stdout, stderr = _run(
        [
            "sudo", "docker", "run", "--rm", "--network", "none",
            "--entrypoint", "python",
            "-v", f"{script}:/tmp/audit_image_contents.py:ro",
            reference,
            "/tmp/audit_image_contents.py", "--runtime", runtime,
        ]
    )
    try:
        report = json.loads(stdout)
    except json.JSONDecodeError:
        detail = stderr.strip()[:200]
        return {"ok": False, "error": f"audit produced no report (exit {code}): {detail}"}
    report["exit_code"] = code
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record immutable image evidence")
    parser.add_argument("--runtime", required=True, choices=("sb3", "mjx"))
    parser.add_argument("--repository", required=True, help="Registry repository, without a tag")
    parser.add_argument("--tag", required=True, help="Immutable commit-SHA tag")
    parser.add_argument("--registry-id", required=True)
    parser.add_argument("--revision", required=True, help="Commit the image was built from")
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--state-root", type=Path, default=Path(".showcase-campaigns"))
    parser.add_argument(
        "--audit-script",
        type=Path,
        default=Path(__file__).resolve().parent / "audit_image_contents.py",
    )
    # The builder that holds the image and the VM that can call the registry API
    # are not always the same machine. When they differ, the digest resolved on the
    # other approved Nebius resource is passed in together with that resource's
    # identity, so the document still names where the registry was read.
    parser.add_argument("--registry-digest")
    parser.add_argument("--registry-digest-resource")
    args = parser.parse_args(argv)
    if bool(args.registry_digest) != bool(args.registry_digest_resource):
        parser.error("--registry-digest and --registry-digest-resource must be given together")

    attestation = require_nebius_execution("verification")
    store = CampaignStore(args.state_root, args.campaign_id)
    reference = f"{args.repository}:{args.tag}"

    if args.registry_digest:
        registry_digest: str | None = args.registry_digest
        source = f"nebius-registry via {args.registry_digest_resource}"
    else:
        registry_digest, source = _registry_digest(args.registry_id, args.tag)
    local_digest = _local_digest(reference)
    digest = registry_digest or local_digest
    # A local-only digest proves nothing about what a job would pull, so the two
    # must agree before the document claims the image is immutable.
    digests_agree = bool(registry_digest) and registry_digest == local_digest

    audit: dict[str, Any] = {"ok": False, "error": "not run"}
    if digest:
        audit = _image_audit(f"{args.repository}@{digest}", args.runtime, args.audit_script)

    document = {
        "runtime": args.runtime,
        "tag": reference,
        "digest": digest,
        "digest_source": source if registry_digest else "local-only",
        "registry_digest": registry_digest,
        "local_digest": local_digest,
        "digests_agree": digests_agree,
        "revision": args.revision,
        "recorded_at": utc_now(),
        "location_attestation": attestation.to_dict(),
        "content_audit": audit,
        "ok": bool(digest) and digests_agree and bool(audit.get("ok")),
    }
    path = store.evidence_path(f"{args.runtime}-image.json")
    store.write_json(path, document)
    write_location_attestation(
        store.evidence_path(f"{args.runtime}-image-location.json"), attestation
    )
    print(json.dumps(store.safe(document), indent=2, sort_keys=True))
    return 0 if document["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
