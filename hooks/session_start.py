#!/usr/bin/env python3
"""SessionStart hook: print the home's last log heading and its age, its State:/Next: (read
by the checker's own log parser), the plugin version, and any checker problems. Opened above
several homes, print one line naming them. Never blocks (SessionStart can't block anyway)."""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    PLUGIN_ROOT, find_home, find_homes_nearby, read_stdin_json, run_checker,
    setup_already_offered,
)


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

    try:
        import check_docs
        entries = check_docs.log_entries(check_docs.Ctx(home, dict(check_docs.CONFIG)))
        if entries:
            heading = entries[-1][1]
            print(heading)
            m = re.search(r"\d{4}-\d{2}-\d{2}", heading)
            try:
                if m:
                    days = (date.today() - date.fromisoformat(m.group())).days
                    print(f"Last entry: {m.group()} ({days} days ago)")
            except ValueError:  # an impossible date: print no age, keep State/Next
                pass
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
