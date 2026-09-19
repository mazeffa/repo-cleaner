#!/usr/bin/env python3
"""Stop hook: force the session's log entry to exist and the checker to pass before
Claude goes quiet, when it changed files this session. Exit 0 = let it stop. Exit 2 =
block, with the reason printed for Claude to act on. Reading or answering without
editing anything writes nothing and never blocks.

Retries are capped: after MAX_RETRIES straight blocks with no progress (e.g. a finding
Claude can't fix, like a missing decisions file), the hook fails open with a warning
instead of wedging the session shut forever.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (
    checker_drift_summary, entry_has_placeholder, entry_line_no, ensure_entry, latest_log_file,
    load_session, read_stdin_json, run_checker, save_session,
)

MAX_RETRIES = 3


def main():
    data = read_stdin_json()
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
        session["retries"] = 0  # new edits are progress; reset the retry budget
    session["pending"] = True

    findings = run_checker(cwd)
    checker_clean = not (findings and findings[0] != 0)
    placeholder = entry_has_placeholder(log, session)

    if not placeholder and checker_clean:
        session["pending"] = False
        session["retries"] = 0
        save_session(session_id, session)
        return 0

    reasons = []
    if placeholder:
        reasons.append('the headline and/or State: sentence are still "TBD"')
    if not checker_clean:
        reasons.append(f"the checker found issues:\n{findings[1].strip()}")
    drift = checker_drift_summary(cwd)
    if drift:
        reasons.append(f"note: the checker that ran differs from the plugin's ({drift})")
    reason_text = "; ".join(reasons)

    rel = log.relative_to(cwd)
    line_no = entry_line_no(log, session)
    retries = session.get("retries", 0) + 1
    session["retries"] = retries
    save_session(session_id, session)

    if retries > MAX_RETRIES:
        print(
            f"repo-clean: giving up after {MAX_RETRIES} tries, letting the session stop "
            f"anyway (entry passed unverified). {rel} line {line_no} still needs a human "
            f"look: {reason_text}",
            file=sys.stderr,
        )
        session["pending"] = False
        session["retries"] = 0
        save_session(session_id, session)
        return 0

    print(f"Entry at {rel} line {line_no} is not ready: {reason_text}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
