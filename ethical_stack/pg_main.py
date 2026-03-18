from __future__ import annotations

from ethical_stack.pggame.app import run_game


def main(headless: bool = False) -> int:
    run_game(headless=headless)
    return 0

