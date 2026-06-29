import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_dry_run_and_missing_parameter() -> None:
    script = ROOT / "jobs/submit.sh"
    missing = subprocess.run(
        [script], capture_output=True, text=True, env={"PATH": os.environ["PATH"]}
    )
    assert missing.returncode == 2
    env = {
        "PATH": os.environ["PATH"],
        "IMAGE": "example/image:tag",
        "CONFIG": "configs/smoke_sb3.yaml",
        "RUN_ID": "safe-run",
        "PLATFORM": "gpu-l40s-d",
        "PRESET": "1gpu-16vcpu-200gb",
        "TIMEOUT": "1h",
        "SUBNET_ID": "subnet",
        "DRY_RUN": "1",
        "S3_SECRET": "secret-id",
    }
    preview = subprocess.run([script], capture_output=True, text=True, env=env)
    assert preview.returncode == 0
    assert "nebius" in preview.stdout
    assert "secret-id" not in preview.stdout

    unsafe = dict(env, RUN_ID="../unsafe")
    rejected = subprocess.run([script], capture_output=True, text=True, env=unsafe)
    assert rejected.returncode == 2

    spaced = dict(env, IMAGE="registry.example/team image:tag")
    escaped = subprocess.run([script], capture_output=True, text=True, env=spaced)
    assert escaped.returncode == 0
    assert "team\\ image" in escaped.stdout
