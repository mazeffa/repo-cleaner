#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write|MultiEdit|NotebookEdit): record which file changed for
this session. No output, no cost - the Stop hook does the bookkeeping later."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import add_file


def main():
    data = json.load(sys.stdin)
    session_id = data.get("session_id")
    file_path = (data.get("tool_input") or {}).get("file_path")
    cwd = Path(data.get("cwd") or ".").resolve()
    if session_id and file_path:
        try:
            file_path = Path(file_path).resolve().relative_to(cwd).as_posix()
        except ValueError:
            file_path = Path(file_path).as_posix()  # outside cwd; record as given
        add_file(session_id, file_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
