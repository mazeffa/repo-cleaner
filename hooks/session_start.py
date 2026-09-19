#!/usr/bin/env python3
"""SessionStart hook: point Claude at repo-clean if it's missing, or remind it of the
current State: line if it's present. Never blocks (SessionStart can't block anyway)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import checker_path, last_state_line


def main():
    data = json.load(sys.stdin)
    cwd = Path(data.get("cwd") or ".").resolve()

    if not (cwd / "CLAUDE.md").exists() or checker_path(cwd) is None:
        print("repo-clean is not set up here. Ask the user, then run /repo-clean init.")
        return 0

    state = last_state_line(cwd)
    if state:
        print(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
