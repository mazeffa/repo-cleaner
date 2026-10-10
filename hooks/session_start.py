#!/usr/bin/env python3
"""SessionStart hook: print the home's current State:/Next:, any checker findings, and -
on a fresh start only - the earlier sessions waiting to be folded in (D-021). Opened
above several homes, print one line naming the ones with un-folded work. Never blocks
(SessionStart can't block anyway)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    NEXT_RE, find_home, find_homes_nearby, last_field, last_state_line, local_time,
    migrate_already_offered, read_stdin_json, run_checker, setup_already_offered,
    unfolded_sessions,
)

FOLD = Path(__file__).resolve().parent / "fold.py"
TRIGGERS = ('Fold-in also runs when the user asks ("/repo-clean maintain", "fold in") '
            'or says the session is over.')


def names(homes):
    shown = ", ".join(h.name for h in homes[:3])
    return shown + (f" and {len(homes) - 3} more" if len(homes) > 3 else "")


def main():
    data = read_stdin_json()
    cwd = Path(data.get("cwd") or ".").resolve()
    startup = data.get("source", "startup") == "startup"

    home, is_legacy = find_home(cwd)
    if home is None:
        nearby = find_homes_nearby(cwd)
        waiting = [h for h in nearby if unfolded_sessions(h)]
        if waiting and startup:
            print(f"repo-clean: {len(waiting)} home(s) below have un-folded sessions: "
                  f"{names(waiting)}. Fold each in (/repo-clean maintain) unless the user "
                  f"says not now. {TRIGGERS}")
        elif nearby:
            print(f"repo-clean: homes below: {names(nearby)}.")
        elif not setup_already_offered(cwd):
            print("repo-clean is not set up here. Ask the user, then run /repo-clean init.")
        return 0

    if is_legacy and not migrate_already_offered(home):
        print(f"{home} is a repo-clean home from before the `.repo-clean` marker. Run "
              "/repo-clean init --migrate to add it and drop the vendored checker.")

    for line in (last_state_line(home), last_field(home, NEXT_RE)):
        if line:
            print(line)

    if startup:
        waiting = unfolded_sessions(home)
        if waiting:
            dates = sorted({s["last_stop"] for s in waiting})
            print(f"repo-clean: {len(waiting)} earlier session(s) not yet folded into the docs "
                  f"(last active {local_time(dates[0])[:10]} to {local_time(dates[-1])[:10]}). "
                  f"Before other work, fold them in per /repo-clean maintain "
                  f"(`python \"{FOLD}\" list`), unless the user says not now - other windows "
                  f"may still be open. {TRIGGERS}")

    sys.stdout.flush()  # the checker is the slow part; what's above survives a timeout
    result = run_checker(home)
    if result and result[0] != 0:
        print(f"repo-clean: the checker found problems in this home - raise them before "
              f"other work:\n{result[1].strip()}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
