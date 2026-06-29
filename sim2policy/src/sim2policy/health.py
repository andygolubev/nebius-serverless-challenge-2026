from __future__ import annotations

import argparse
import importlib
import json
import shutil
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["base", "sb3", "mjx"], default="base")
    args = parser.parse_args(argv)
    modules = ["sim2policy", "boto3", "yaml"]
    if args.backend == "sb3": modules += ["torch", "gymnasium", "stable_baselines3", "mujoco"]
    if args.backend == "mjx": modules += ["jax", "mujoco", "mujoco_playground"]
    versions = {}
    for name in modules:
        module = importlib.import_module(name)
        versions[name] = getattr(module, "__version__", "installed")
    if args.backend == "mjx":
        import jax  # type: ignore[import-not-found]
        versions["jax_backend"] = jax.default_backend()
    if args.backend == "sb3":
        import torch  # type: ignore[import-not-found]
        versions["cuda_available"] = torch.cuda.is_available()
        versions["cuda_version"] = torch.version.cuda
    versions["ffmpeg"] = shutil.which("ffmpeg") or "imageio-managed"
    print(json.dumps(versions, indent=2, sort_keys=True))


if __name__ == "__main__": main()

