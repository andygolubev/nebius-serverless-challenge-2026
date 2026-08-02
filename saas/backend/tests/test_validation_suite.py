"""Regression tests for deterministic validation inventory and sanitized reports."""

from __future__ import annotations

import json
from pathlib import Path

from validation_suite.matrix import manifest, positive_setup_cases, select_shard
from validation_suite.report import build_report, parse_junit, scan_paths


def _junit(path: Path, names: list[str]) -> Path:
    cases = "".join(
        f'<testcase classname="matrix" name="[{name}]" time="0.01" />'
        for name in names
    )
    path.write_text(f'<testsuite tests="{len(names)}">{cases}</testsuite>', encoding="utf-8")
    return path


def test_manifest_counts_and_four_way_shards_are_complete() -> None:
    inventory = manifest()
    assert inventory["counts"] == {
        "positive_setups": 100,
        "eligible_setups": 100,
        "object_parameters": 28,
        "parameter_cases": 140,
        "non_finite_parameter_cases": 84,
        "capacity_cases": 8,
        "controls": 32,
    }
    cases = positive_setup_cases()
    shards = [select_shard(cases, index=index, total=4) for index in range(4)]
    merged = [case.case_id for shard in shards for case in shard]
    assert sorted(merged) == sorted(case.case_id for case in cases)
    assert len(merged) == len(set(merged))


def test_report_detects_duplicate_and_missing_case_ids(tmp_path: Path) -> None:
    first = _junit(tmp_path / "one.xml", ["api:case:one", "api:case:duplicate"])
    second = _junit(tmp_path / "two.xml", ["api:case:duplicate"])
    report = build_report(
        [first, second],
        run_id="unit",
        expected_ids=["api:case:one", "api:case:duplicate", "api:case:missing"],
    )
    assert report["duplicate_case_ids"] == ["api:case:duplicate"]
    assert report["missing_case_ids"] == ["api:case:missing"]
    assert [case["case_id"] for case in parse_junit(first)] == [
        "api:case:one",
        "api:case:duplicate",
    ]


def test_evidence_scan_blocks_private_content_and_unscannable_files(tmp_path: Path) -> None:
    private = tmp_path / "failure.txt"
    private.write_text("authorization: Bearer token-shaped-value-123456", encoding="utf-8")
    binary = tmp_path / "screenshot.bin"
    binary.write_bytes(b"\xff\xfe\xfd")
    findings = scan_paths([tmp_path])
    assert findings[str(private)] == ["authorization-header", "bearer-token"]
    assert findings[str(binary)] == ["unscannable-artifact"]


def test_manifest_is_json_serializable() -> None:
    encoded = json.dumps(manifest(), sort_keys=True)
    assert "catalog_fingerprint" in encoded
