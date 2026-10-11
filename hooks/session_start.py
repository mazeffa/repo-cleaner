#!/usr/bin/env python3
"""SessionStart hook: run the checker once with --summary and print what it says - the open
items in docs/WORK.md, the last log entry, the plugin version, then any finding (D-029(5)).
No git. Opened above several homes, print one line naming them. Never blocks (SessionStart
can't block anyway)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import find_home, find_homes_nearby, read_stdin_json, run_checker, setup_already_offered


def names(homes):
    shown = ", ".join(h.name for h in homes[:3])
    return shown + (f" and {len(homes) - 3} more" if len(homes) > 3 else "")


def main():
    data = read_stdin_json()
    cwd = Path(data.get("cwd") or ".").resolve()

    home = find_home(cwd)
    if home is None:
        nearby = find_homes_nearby(cwd)
        if nearby:
            print(f"repo-clean: homes below: {names(nearby)}.")
        elif not setup_already_offered(cwd):
            print("repo-clean is not set up here. Ask the user, then run /repo-clean init.")
        return 0

    code, text = run_checker(home)
    print(text.strip())
    if code == 124:
        print("repo-clean: the checker timed out - docs not fully checked")
    elif code not in (0, 1):
        print("repo-clean: the checker itself failed - docs not checked")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
