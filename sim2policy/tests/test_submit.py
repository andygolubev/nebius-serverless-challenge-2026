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
        "RESUME": "remote",
        "S3_ACCESS_KEY_ID": "NAKITESTACCESSKEYID",
        "S3_SECRET": "secret-id",
        "S3_BUCKET": "artifacts",
        "S3_ENDPOINT": "https://storage.example",
        "S3_REGION": "test-region",
    }
    preview = subprocess.run([script], capture_output=True, text=True, env=env)
    assert preview.returncode == 0
    assert "nebius" in preview.stdout
    assert "secret-id" not in preview.stdout
    assert "AWS_ACCESS_KEY_ID=NAKITESTACCESSKEYID" in preview.stdout
    assert "AWS_SECRET_ACCESS_KEY=<redacted>" in preview.stdout
    assert "storage.mode" in preview.stdout
    assert "restart-policy never" in preview.stdout
    assert "--resume\\ remote" in preview.stdout

    unsafe = dict(env, RUN_ID="../unsafe")
    rejected = subprocess.run([script], capture_output=True, text=True, env=unsafe)
    assert rejected.returncode == 2

    spaced = dict(env, IMAGE="registry.example/team image:tag")
    escaped = subprocess.run([script], capture_output=True, text=True, env=spaced)
    assert escaped.returncode == 0
    assert "team\\ image" in escaped.stdout

    missing_access_id = dict(env)
    missing_access_id.pop("S3_ACCESS_KEY_ID")
    rejected_credentials = subprocess.run(
        [script], capture_output=True, text=True, env=missing_access_id
    )
    assert rejected_credentials.returncode == 2
    assert "S3_ACCESS_KEY_ID is required" in rejected_credentials.stderr

    invalid_resume = dict(env, RESUME="latest")
    rejected_resume = subprocess.run(
        [script], capture_output=True, text=True, env=invalid_resume
    )
    assert rejected_resume.returncode == 2
    assert "RESUME must be remote" in rejected_resume.stderr
