#!/usr/bin/env python3
"""Stop hook (D-021): record the session against every home it touched - or, with no
edits, the home it opened in - so the next fold-in can find it. If a markdown doc in a
touched home changed since the last check - by any means, not only Claude's edit tool - run
the checker for that home and block on a finding (exit 2, reason on stderr for Claude to fix).
A checker that crashes, is missing or times out is not a finding: nothing blocks, the home
stays marked for the next Stop, and SessionStart prints the problem. Writes no log entry.

`stop_hook_active` means Claude is already continuing because of this hook; the record is
still updated but nothing blocks, so a finding Claude can't fix never wedges the session.
Unchecked docs stay marked and are checked at the next Stop.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import find_home, read_stdin_json, run_checker, save_session, session_homes


def newest_mtime(home):
    """Newest modification time across the checker's own set of docs (living docs plus the
    log), so the hook and the checker agree on what a doc is."""
    try:
        import check_docs
        ctx = check_docs.Ctx(home, dict(check_docs.CONFIG))
        paths = list(check_docs.docs_plus_log(ctx))
    except Exception:
        return float("inf")  # can't tell: run the checker; it reports its own failure as 2
    newest = 0
    for p in paths:
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            pass  # vanished mid-scan: nothing to check in it
    return newest


def needs_check(home, rec):
    """A doc was edited (dirty), or any doc is newer than the last clean check."""
    return bool(rec.get("dirty") or ("checked_at" in rec and newest_mtime(home) > rec["checked_at"]))


def main():
    t0 = time.time()  # Stop's hook limit is 30 s; the checker run must fit in what is left
    data = read_stdin_json()
    session_id = data.get("session_id")
    if not session_id:
        return 0
    touched = session_homes(session_id)
    if not touched:
        home = find_home(Path(data.get("cwd") or ".").resolve())
        if home is None:
            return 0  # opened above every home and edited nothing: nowhere to record it
        touched = [(home, {})]

    blocking = not data.get("stop_hook_active")
    reasons, skipped = [], []
    for home, rec in touched:
        rec["transcript"] = data.get("transcript_path") or rec.get("transcript")
        rec["last_stop"] = time.time()
        if rec.pop("fold_pending", False):
            rec["folded_stop"] = rec["last_stop"]  # this session only folded in; DEF-33
        run = needs_check(home, rec)
        remaining = 27 - (time.time() - t0)
        if run and blocking and remaining < 2:
            skipped.append(str(home))
        if run and blocking and remaining >= 2:
            started = time.time()  # taken before the run, so a doc changed during it is re-checked
            code, out = run_checker(home, timeout=min(25, remaining))
            if code == 0:
                rec["dirty"] = False
                rec["checked_at"] = started
            elif code == 1:
                reasons.append(f"{home}: the checker exited 1:\n{out.strip() or '(no output)'}")
            # 2 (checker failed) or 124 (timed out): not a doc finding - stay marked, retry next Stop
        rec.setdefault("checked_at", t0)  # a record from before 0.10 is covered from its first Stop
        save_session(home, session_id, rec)

    if skipped:
        print(f"repo-clean: {len(skipped)} home(s) not checked this turn (time budget): "
              + ", ".join(skipped), file=sys.stderr)
    if reasons:
        print("repo-clean: fix these doc findings before stopping.\n" + "\n\n".join(reasons),
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
