from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from sim2policy.config import load_config
from sim2policy.reporting import (
    comparison_table,
    load_reward_points,
    threshold_crossing,
    write_reward_curve,
)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    curve = subparsers.add_parser("curve")
    curve.add_argument("--config", required=True)
    curve.add_argument("--run-root", required=True, type=Path)
    compare = subparsers.add_parser("compare")
    compare.add_argument("metrics", nargs="+", type=Path)
    compare.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "curve":
        config = load_config(args.config)
        points = load_reward_points(args.run_root / "tensorboard")
        write_reward_curve(points, args.run_root / "report/reward-curve.png")
        if config.success.threshold is not None:
            crossing = threshold_crossing(points, config.success.threshold)
            (args.run_root / "report/threshold-crossing.json").write_text(
                json.dumps(crossing, indent=2) + "\n"
            )
    else:
        documents = [json.loads(path.read_text()) for path in args.metrics]
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(comparison_table(documents))


if __name__ == "__main__":
    main()
