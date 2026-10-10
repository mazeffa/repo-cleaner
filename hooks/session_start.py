#!/usr/bin/env python3
"""SessionStart hook: print the home's current State:/Next: (read by the checker's own log
parser), the plugin version, any checker problems, and - on a fresh start only - the earlier
sessions waiting to be folded in (D-021). Opened
above several homes, print one line naming the ones with un-folded work. Never blocks
(SessionStart can't block anyway)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    PLUGIN_ROOT, find_home, find_homes_nearby, load_session, local_time, read_stdin_json,
    run_checker, save_session, setup_already_offered, unfolded_sessions,
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

    home = find_home(cwd)
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

    try:
        import check_docs
        fields = check_docs.current_fields(home)
        for key in ("State", "Next"):
            if fields.get(key):
                print(f"{key}: {fields[key]}")
    except Exception as exc:
        print(f"repo-clean: checker import failed: {exc!r}")
    try:
        version = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json")
                             .read_text(encoding="utf-8"))["version"]
        print(f"repo-clean {version}")
    except Exception as exc:
        print(f"repo-clean: version unknown ({exc!r})")

    if startup:
        waiting = unfolded_sessions(home)
        if waiting:
            dates = sorted({s["last_stop"] for s in waiting})
            print(f"repo-clean: {len(waiting)} earlier session(s) not yet folded into the docs "
                  f"(last active {local_time(dates[0])[:10]} to {local_time(dates[-1])[:10]}). "
                  f"Before other work, fold them in per /repo-clean maintain "
                  f"(`python \"{FOLD}\" list \"{home}\"`), unless the user says not now - other windows "
                  f"may still be open. {TRIGGERS}")

    sid = data.get("session_id")
    if sid:  # problems that predate the session are shown below, not used to block its turns
        rec = load_session(home, sid)
        if "checked_at" not in rec:
            rec["checked_at"] = time.time()
            save_session(home, sid, rec)
    sys.stdout.flush()  # the checker is the slow part; what's above survives a timeout
    code, text = run_checker(home)
    if code == 1:
        print(f"repo-clean: the checker found problems in this home - raise them before "
              f"other work:\n{text.strip()}")
    elif code != 0:
        print(f"repo-clean: the checker itself failed ({text.strip()}) - docs not checked")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
