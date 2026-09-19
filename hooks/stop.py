#!/usr/bin/env python3
"""Stop hook: force the session's log entry to exist and the checker to pass before
Claude goes quiet, when it changed files this session. Exit 0 = let it stop. Exit 2 =
block, with the reason printed for Claude to act on. Reading or answering without
editing anything writes nothing and never blocks."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    entry_has_placeholder, entry_line_no, ensure_entry, latest_log_file,
    load_session, run_checker, save_session,
)


def main():
    data = json.load(sys.stdin)
    session_id = data.get("session_id")
    cwd = Path(data.get("cwd") or ".").resolve()
    if not session_id:
        return 0

    session = load_session(session_id)
    files = session.get("files", [])
    pending = session.get("pending", False)
    if not files and not pending:
        return 0  # nothing changed, or already logged clean

    log = latest_log_file(cwd)
    if log is None:
        return 0  # no doc system here; nothing to force

    if files:
        ensure_entry(cwd, session, files)
        session["files"] = []
    session["pending"] = True
    save_session(session_id, session)

    findings = run_checker(cwd)
    findings_msg = f"\n{findings[1].strip()}" if findings and findings[0] != 0 else ""

    if not entry_has_placeholder(log, session) and not findings_msg:
        session["pending"] = False
        save_session(session_id, session)
        return 0

    rel = log.relative_to(cwd)
    line_no = entry_line_no(log, session)
    print(
        f"Entry ready at {rel} line {line_no}. Fill in the headline and one State: sentence."
        f"{findings_msg}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
