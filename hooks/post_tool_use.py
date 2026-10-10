#!/usr/bin/env python3
"""PostToolUse hook (Edit|Write|MultiEdit|NotebookEdit): mark the home the edited file belongs
to as touched (and its docs as changed, for a .md) - resolved from the file's own path, not
the session's working directory, so a session opened above many homes still credits the right
one. It does not record which file. No output, no cost - the Stop hook does the rest."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import add_file, find_home, read_stdin_json


def main():
    data = read_stdin_json()
    session_id = data.get("session_id")
    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not session_id or not file_path:
        return 0
    path = Path(data.get("cwd") or ".", file_path).resolve()
    home = find_home(path.parent)
    if home is None:
        return 0
    add_file(session_id, home, path.relative_to(home).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
