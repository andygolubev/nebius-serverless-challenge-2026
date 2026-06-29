from __future__ import annotations

import argparse
from collections.abc import Sequence

from sim2policy import __version__
from sim2policy.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sim2policy")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-config", help="validate and resolve a YAML config")
    validate.add_argument("config")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "validate-config":
        config = load_config(args.config)
        print(config.to_yaml(), end="")


if __name__ == "__main__":
    main()
