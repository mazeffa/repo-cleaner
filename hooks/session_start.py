#!/usr/bin/env python3
"""SessionStart hook: point Claude at repo-clean if it's missing, or remind it of the
current State: line if it's present. Never blocks (SessionStart can't block anyway)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    carry_over_orphans, checker_drift, checker_path, drift_unreported, last_state_line,
    read_stdin_json, setup_already_offered,
)


def main():
    data = read_stdin_json()
    session_id = data.get("session_id")
    cwd = Path(data.get("cwd") or ".").resolve()

    if not (cwd / "CLAUDE.md").exists() or checker_path(cwd) is None:
        if not setup_already_offered(cwd):
            print("repo-clean is not set up here. Ask the user, then run /repo-clean init.")
        return 0

    if session_id:
        carried = carry_over_orphans(session_id, cwd)
        if carried:
            print(f"Carried {carried} unlogged changes from a previous session")

    drift = checker_drift(cwd)
    if drift and drift_unreported(cwd, drift):
        print(drift)

    state = last_state_line(cwd)
    if state:
        print(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
