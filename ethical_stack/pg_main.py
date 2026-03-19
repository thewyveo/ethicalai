from __future__ import annotations

from ethical_stack.pggame.app import run_game


def main(headless: bool = False) -> int:
    import os
    admin_phase2 = os.environ.get("ADMIN_PHASE2", "").strip().lower() in ("1", "true", "yes", "on")
    run_game(headless=headless, admin_phase2=admin_phase2)
    return 0

