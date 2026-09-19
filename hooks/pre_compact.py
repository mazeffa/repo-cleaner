#!/usr/bin/env python3
"""PreCompact hook: fold any pending session edits into the log entry before context is
lost, so a compaction never drops the record of what changed. Non-blocking - compaction
can't be refused, this just makes sure there's something to resume from."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import ensure_entry, load_session, read_stdin_json, save_session


def main():
    data = read_stdin_json()
    session_id = data.get("session_id")
    cwd = Path(data.get("cwd") or ".").resolve()
    if not session_id:
        return 0

    session = load_session(session_id)
    files = session.get("files", [])
    if files:
        ensure_entry(cwd, session, files)
        session["files"] = []
        session["pending"] = True
        save_session(session_id, session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
