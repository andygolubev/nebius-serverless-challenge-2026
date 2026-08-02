"""Merge test evidence into sanitized My Robots validation JSON and Markdown."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree

from .matrix import catalog_fingerprint

CASE_ID_RE = re.compile(r"(?:case_id=|\[)([a-z0-9][a-z0-9._:-]+)\]?")
SENSITIVE_PATTERNS = {
    "authorization-header": re.compile(r"authorization\s*:\s*bearer\s+\S+", re.I),
    "bearer-token": re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]{16,}", re.I),
    "email-code": re.compile(r"\b(?:login|verification|one[- ]time)\s+code\D{0,12}\d{6}\b", re.I),
    "private-xml": re.compile(r"<(?:mujoco|worldbody|actuator)(?:\s|>)", re.I),
    "secret-selector": re.compile(r"\b(?:secret|version)-[A-Za-z0-9._-]{8,}\b"),
    "storage-key": re.compile(r"\b(?:s3|sim2policy)/(?:runs|preparations)/[^\s\"']+", re.I),
    "aws-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
}


def _case_id(classname: str, name: str, layer: str) -> str:
    match = CASE_ID_RE.search(name)
    if match:
        return match.group(1)
    normalized = re.sub(r"[^a-z0-9]+", "-", f"{classname}-{name}".lower()).strip("-")
    digest = hashlib.sha256(f"{classname}\0{name}".encode()).hexdigest()[:10]
    return f"{layer}:test:{normalized[:80]}:{digest}"


def parse_junit(path: Path, *, layer: str | None = None) -> list[dict[str, Any]]:
    root = ElementTree.parse(path).getroot()
    inferred_layer = layer or path.stem.replace("_", "-")
    cases: list[dict[str, Any]] = []
    for testcase in root.iter("testcase"):
        name = testcase.attrib.get("name", "unnamed")
        classname = testcase.attrib.get("classname", "")
        status = "passed"
        diagnostic = None
        for child_status, element_name in (
            ("failed", "failure"),
            ("error", "error"),
            ("skipped", "skipped"),
        ):
            element = testcase.find(element_name)
            if element is not None:
                status = child_status
                diagnostic = (element.attrib.get("message") or element_name)[:500]
                break
        cases.append(
            {
                "case_id": _case_id(classname, name, inferred_layer),
                "layer": inferred_layer,
                "status": status,
                "duration_seconds": float(testcase.attrib.get("time", "0") or 0),
                "diagnostic": diagnostic,
                "source": path.name,
            }
        )
    return cases


def scan_text(text: str) -> list[str]:
    return [name for name, pattern in SENSITIVE_PATTERNS.items() if pattern.search(text)]


def scan_paths(paths: Iterable[Path]) -> dict[str, list[str]]:
    findings: dict[str, list[str]] = {}
    for path in paths:
        candidates = sorted(path.rglob("*")) if path.is_dir() else [path]
        for candidate in candidates:
            if not candidate.is_file() or candidate.stat().st_size > 10 * 1024 * 1024:
                continue
            try:
                text = candidate.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            matched = scan_text(text)
            if matched:
                findings[str(candidate)] = matched
    return findings


def build_report(
    junit_paths: Iterable[Path],
    *,
    run_id: str,
    cost_gates: dict[str, str] | None = None,
) -> dict[str, Any]:
    cases = [case for path in junit_paths for case in parse_junit(path)]
    identifiers = [case["case_id"] for case in cases]
    duplicates = sorted(case_id for case_id, count in Counter(identifiers).items() if count > 1)
    summary = Counter(case["status"] for case in cases)
    return {
        "schema_version": 1,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_fingerprint": catalog_fingerprint(),
        "summary": dict(sorted(summary.items())),
        "duplicate_case_ids": duplicates,
        "cost_gates": cost_gates
        or {
            "remote_preparation": "not-run-cost-gated",
            "remote_training": "not-run-cost-gated",
        },
        "resources": {"created": [], "deleted": []},
        "cleanup": {"status": "not-applicable", "remaining": []},
        "cases": sorted(cases, key=lambda case: (case["case_id"], case["layer"])),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# My Robots validation report",
        "",
        f"- Run: `{report['run_id']}`",
        f"- Catalog: `{report['catalog_fingerprint']}`",
        f"- Passed: {summary.get('passed', 0)}",
        f"- Failed: {summary.get('failed', 0) + summary.get('error', 0)}",
        f"- Skipped: {summary.get('skipped', 0)}",
        f"- Remote preparation: `{report['cost_gates']['remote_preparation']}`",
        f"- Remote training: `{report['cost_gates']['remote_training']}`",
        f"- Cleanup: `{report['cleanup']['status']}`",
        "",
        "## Non-passing cases",
        "",
    ]
    non_passing = [case for case in report["cases"] if case["status"] != "passed"]
    if non_passing:
        for case in non_passing:
            lines.append(
                f"- `{case['case_id']}` — {case['status']}: {case['diagnostic'] or 'no diagnostic'}"
            )
    else:
        lines.append("None.")
    if report["duplicate_case_ids"]:
        lines.extend(
            ("", "## Duplicate case IDs", "", *[f"- `{item}`" for item in report["duplicate_case_ids"]])
        )
    return "\n".join(lines) + "\n"


def _write_report(report: dict[str, Any], output: Path, markdown: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    findings = scan_text(rendered)
    if findings:
        raise ValueError(f"refusing to write sensitive report categories: {findings}")
    output.write_text(rendered, encoding="utf-8")
    markdown.write_text(render_markdown(report), encoding="utf-8")


def _main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    merge = subparsers.add_parser("merge")
    merge.add_argument("--junit", action="append", required=True, type=Path)
    merge.add_argument("--run-id", required=True)
    merge.add_argument("--output", required=True, type=Path)
    merge.add_argument("--markdown", required=True, type=Path)
    scan = subparsers.add_parser("scan")
    scan.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "scan":
        findings = scan_paths(args.paths)
        if findings:
            print(json.dumps(findings, indent=2, sort_keys=True), file=sys.stderr)
            return 1
        return 0
    report = build_report(args.junit, run_id=args.run_id)
    if report["duplicate_case_ids"]:
        print(
            f"duplicate case IDs: {', '.join(report['duplicate_case_ids'])}",
            file=sys.stderr,
        )
        return 1
    _write_report(report, args.output, args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
