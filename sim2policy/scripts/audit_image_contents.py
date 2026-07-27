"""Prove what a built runtime image does and does not contain (task 7.5).

Runs *inside* the image, so its answers describe the artifact that will actually
be submitted rather than the builder's working tree. Two questions, both of which
have to be answered before a paid job is legal:

* **Is everything the plan needs present?** Every config path and module the
  campaign matrix names must exist and import, because a missing one becomes a
  crashed job minutes into paid compute.
* **Is anything present that must not be?** A credential baked into a layer is
  permanently published to everyone who can pull the image, and a generated
  checkpoint, run directory, or video baked in would make a fresh training result
  indistinguishable from a stale one.

Output is a single JSON document on stdout. Nothing is written, nothing is
network-reachable, and no matched value is ever printed — only its path.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

#: Modules the campaign's submitted commands enter through.
REQUIRED_MODULES = (
    "sim2policy.hosted_sb3",
    "sim2policy.hosted_mjx",
    "sim2policy.hosted_g1_curriculum",
    "sim2policy.finalize",
    "sim2policy.checkpoint_selection",
    "sim2policy.policy_bundle",
    "sim2policy.storage",
    "sim2policy.execution_location",
)

#: Filenames that are credentials by name wherever they appear.
SECRET_FILE_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".netrc",
        ".git-credentials",
        "credentials",
        "terraform.tfvars",
        "tofu-backend.env",
        "terraform.tfstate",
        "saas.db",
    }
)
#: Suffixes that *may* hold a key. Confirmed by content, because a `.pem` is just
#: as often a public CA trust bundle shipped by a dependency.
KEY_BEARING_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
#: Suffixes that are secret-bearing regardless of content.
SECRET_FILE_SUFFIXES = (".tfstate", ".tfplan")
SECRET_DIRECTORY_NAMES = frozenset({".aws", ".ssh", ".docker", ".nebius"})
SECRET_DIRECTORY_PATHS = (".config/sim2policy",)

#: Generated training output that must never be part of an image layer.
ARTIFACT_DIRECTORY_NAMES = frozenset({"runs", "outputs", "checkpoints", "wandb", "mlruns"})
ARTIFACT_SUFFIXES = (".ckpt", ".pt", ".pth", ".msgpack", ".mp4", ".webm", ".gif", ".npz")

#: Credential syntax scanned for in text files under the application tree.
SECRET_CONTENT_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("aws_access_key_id", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("jwt_or_iam_token", re.compile(rb"\beyJ[A-Za-z0-9._-]{40,}")),
    ("private_key_block", re.compile(rb"-----BEGIN[A-Z ]*PRIVATE KEY-----")),
    ("bearer_header", re.compile(rb"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{16,}")),
)

#: Text files large enough to be data, not source, are not content-scanned.
_MAX_SCAN_BYTES = 2_000_000
_SCAN_SUFFIXES = frozenset({".py", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".txt", ".sh", ".md"})


def _matrix_paths(app: Path, matrix_relative: str) -> tuple[list[str], str | None]:
    """Every config path the reviewed matrix names, including the G1 curriculum."""
    matrix_path = app / matrix_relative
    if not matrix_path.is_file():
        return [], f"matrix not found at {matrix_relative}"
    matrix = yaml.safe_load(matrix_path.read_text(encoding="utf-8")) or {}
    paths = {matrix_relative}
    for card in (matrix.get("examples") or {}).values():
        if not isinstance(card, dict):
            continue
        if card.get("config"):
            paths.add(str(card["config"]))
        curriculum = card.get("curriculum") or {}
        for key in ("flat_config", "rough_config"):
            if curriculum.get(key):
                paths.add(str(curriculum[key]))
    return sorted(paths), None


def _check_configs(app: Path, matrix_relative: str) -> dict[str, Any]:
    paths, error = _matrix_paths(app, matrix_relative)
    missing = [relative for relative in paths if not (app / relative).is_file()]
    return {
        "matrix": matrix_relative,
        "expected": paths,
        "missing": missing,
        "ok": bool(paths) and not missing and error is None,
        **({"error": error} if error else {}),
    }


def _check_modules() -> dict[str, Any]:
    """Resolve each entry-point module without importing heavy runtime graphs."""
    missing = []
    for name in REQUIRED_MODULES:
        try:
            found = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            found = False
        if not found:
            missing.append(name)
    return {"expected": list(REQUIRED_MODULES), "missing": missing, "ok": not missing}


def _walk(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            yield path


def _holds_private_key(path: Path) -> bool:
    """A key-shaped file is only a finding if it actually carries a private key.

    Dependencies ship public CA bundles as `.pem`; flagging those would train the
    reader to ignore this check, which is worse than not having it.
    """
    try:
        if path.stat().st_size > _MAX_SCAN_BYTES:
            return True  # too large to clear; report rather than assume
        blob = path.read_bytes()
    except OSError:
        return True
    return b"PRIVATE KEY-----" in blob


def _check_secrets(roots: list[Path], app: Path) -> dict[str, Any]:
    """Report the *paths* of credential-shaped files and matches, never values."""
    by_name: list[str] = []
    for path in _walk(roots):
        if path.is_dir():
            named = path.name in SECRET_DIRECTORY_NAMES or str(path).endswith(SECRET_DIRECTORY_PATHS)
            if named and any(path.iterdir()):
                by_name.append(str(path))
            continue
        if path.name in SECRET_FILE_NAMES or path.suffix in SECRET_FILE_SUFFIXES:
            by_name.append(str(path))
        elif path.suffix in KEY_BEARING_SUFFIXES and _holds_private_key(path):
            by_name.append(str(path))

    by_content: list[dict[str, str]] = []
    for path in app.rglob("*"):
        if not path.is_file() or path.suffix not in _SCAN_SUFFIXES:
            continue
        try:
            if path.stat().st_size > _MAX_SCAN_BYTES:
                continue
            blob = path.read_bytes()
        except OSError:
            continue
        for label, pattern in SECRET_CONTENT_PATTERNS:
            if pattern.search(blob):
                by_content.append({"path": str(path), "pattern": label})
    # Field names deliberately avoid the words the campaign redactor treats as
    # credential-shaped keys: a check reported as `<redacted>` proves nothing.
    return {
        "flagged_files": sorted(by_name),
        "flagged_matches": sorted(by_content, key=lambda item: item["path"]),
        "ok": not by_name and not by_content,
    }


def _check_training_artifacts(app: Path) -> dict[str, Any]:
    """No run directory, checkpoint, or rendered video may be baked into a layer."""
    found: list[str] = []
    for path in app.rglob("*"):
        if path.is_dir() and path.name in ARTIFACT_DIRECTORY_NAMES and any(path.iterdir()):
            found.append(str(path))
        elif path.is_file() and path.suffix in ARTIFACT_SUFFIXES:
            found.append(str(path))
        elif path.is_file() and path.suffix == ".zip" and "test" not in str(path):
            # SB3 saves policies as `.zip`; a fixture under tests is expected.
            found.append(str(path))
    return {"found": sorted(found), "ok": not found}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a built runtime image's contents")
    parser.add_argument("--runtime", required=True, choices=("sb3", "mjx"))
    parser.add_argument("--app", default="/app")
    parser.add_argument("--matrix", default="configs/showcase_training_matrix.yaml")
    parser.add_argument(
        "--scan-root",
        action="append",
        default=None,
        help="Additional filesystem root to scan for credential-shaped files.",
    )
    args = parser.parse_args(argv)

    app = Path(args.app)
    roots = [Path(root) for root in (args.scan_root or ["/app", "/root", "/home", "/opt/venv/etc"])]
    checks = {
        "configs": _check_configs(app, args.matrix),
        "modules": _check_modules(),
        "key_material": _check_secrets(roots, app),
        "training_artifacts": _check_training_artifacts(app),
    }
    report = {
        "runtime": args.runtime,
        "app": str(app),
        "python": sys.version.split()[0],
        "checks": checks,
        "ok": all(check["ok"] for check in checks.values()),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
