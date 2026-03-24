from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ethical_stack", add_help=True)
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Force dummy SDL drivers (no real window). Useful in CI/sandboxes.",
    )
    args, _ = parser.parse_known_args(argv)

    headless = args.headless or (not sys.stdin.isatty())
    if headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    from ethical_stack.pg_main import main as pg_main

    return pg_main(headless=headless)
