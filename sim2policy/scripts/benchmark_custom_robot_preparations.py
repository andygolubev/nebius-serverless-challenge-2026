"""Run the fixed preparation entrypoint across the canonical matrix and negative gates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sim2policy.custom_robot_contract import (
    ADAPTER_VERSION,
    PREPARATION_PROFILE_VERSION,
    REWARD_VERSION,
    SCHEMA_VERSION,
    canonical_json,
    preparation_fingerprint,
    sha256_bytes,
)


def _samples() -> Path:
    mounted = Path("/samples")
    if mounted.is_dir():
        return mounted
    return Path(__file__).resolve().parents[2] / "saas" / "samples" / "robots"


def _write_inputs(
    root: Path,
    *,
    identity: str,
    robot_xml: bytes,
    robot_type: str,
    task: str,
    scene: str,
    tamper_robot_after_manifest: bool = False,
) -> Path:
    inputs = root / identity / "inputs"
    inputs.mkdir(parents=True)
    setup = canonical_json(
        {
            "objects": [],
            "robot_type": robot_type,
            "scene_preset_id": scene,
            "schema_version": SCHEMA_VERSION,
            "task_template_id": task,
        }
    )
    runtime = "registry.example/sim2policy@sha256:" + "a" * 64
    robot_digest = sha256_bytes(robot_xml)
    setup_digest = sha256_bytes(setup)
    manifest = canonical_json(
        {
            "adapter_version": ADAPTER_VERSION,
            "fingerprint": preparation_fingerprint(
                robot_digest=robot_digest,
                setup_digest=setup_digest,
                runtime_image_digest=runtime,
            ),
            "preparation_id": identity,
            "preparation_profile_version": PREPARATION_PROFILE_VERSION,
            "reward_version": REWARD_VERSION,
            "robot": {
                "id": f"robot-{robot_type}",
                "path": "robot.xml",
                "sha256": robot_digest,
                "size_bytes": len(robot_xml),
                "source_digest": robot_digest,
            },
            "runtime": {"image_digest": runtime},
            "schema_version": SCHEMA_VERSION,
            "setup": {
                "id": f"setup-{identity}",
                "path": "normalized-setup.json",
                "sha256": sha256_bytes(setup),
                "size_bytes": len(setup),
                "source_digest": setup_digest,
            },
        }
    )
    (inputs / "input-manifest.json").write_bytes(manifest)
    (inputs / "normalized-setup.json").write_bytes(setup)
    (inputs / "robot.xml").write_bytes(
        b"X" + robot_xml[1:] if tamper_robot_after_manifest else robot_xml
    )
    return inputs


def _run_case(root: Path, identity: str, inputs: Path) -> dict[str, object]:
    output = root / identity / "output"
    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "sim2policy.custom_robot_job",
            "prepare",
            "--identity",
            identity,
            "--input-root",
            str(inputs),
            "--output-root",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=900,
    )
    report_path = output / "report" / "preparation.json"
    report = json.loads(report_path.read_text()) if report_path.is_file() else None
    return {
        "identity": identity,
        "returncode": result.returncode,
        "wall_seconds": round(time.monotonic() - started, 3),
        "status": None if report is None else report["status"],
        "failure_phase": None if report is None else report["failure_phase"],
        "failure_reason": None if report is None else report["failure_reason"],
        "phase_seconds": (
            {}
            if report is None
            else {phase["name"]: phase["duration_seconds"] for phase in report["phases"]}
        ),
        "stderr": result.stderr.strip(),
    }


def main() -> None:
    samples = _samples()
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="custom-robot-matrix-") as temporary:
        root = Path(temporary)
        for robot_type in ("biped", "quadruped"):
            robot_xml = (samples / f"sample-{robot_type}.xml").read_bytes()
            for task in ("stand-balance", "walk-forward"):
                for scene in ("flat-arena", "ramp-course"):
                    identity = f"canonical-{robot_type}-{task}-{scene}"
                    inputs = _write_inputs(
                        root,
                        identity=identity,
                        robot_xml=robot_xml,
                        robot_type=robot_type,
                        task=task,
                        scene=scene,
                    )
                    result = _run_case(root, identity, inputs)
                    assert result["returncode"] == 0 and result["status"] == "accepted", result
                    results.append(result)

        biped = (samples / "sample-biped.xml").read_bytes()
        unsupported = biped.replace(b'ctrlrange="-1 1"', b'ctrlrange="-100000 100000"')
        inputs = _write_inputs(
            root,
            identity="negative-control-range",
            robot_xml=unsupported,
            robot_type="biped",
            task="stand-balance",
            scene="flat-arena",
        )
        result = _run_case(root, "negative-control-range", inputs)
        assert result["returncode"] == 2
        assert result["failure_reason"] == "actuator-control-range-invalid"
        results.append(result)

        inputs = _write_inputs(
            root,
            identity="negative-digest-tamper",
            robot_xml=biped,
            robot_type="biped",
            task="stand-balance",
            scene="flat-arena",
            tamper_robot_after_manifest=True,
        )
        result = _run_case(root, "negative-digest-tamper", inputs)
        assert result["returncode"] == 2
        assert result["status"] is None
        assert result["stderr"] == "custom robot prepare failed: input-contract-failed"
        results.append(result)

    for result in results:
        print(json.dumps(result, sort_keys=True))
    print(f"fixed preparation entrypoint matrix: {len(results) - 2}/8 accepted, 2/2 rejected")


if __name__ == "__main__":
    main()
