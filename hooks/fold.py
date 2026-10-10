#!/usr/bin/env python3
"""Fold-in helper (D-021), run by Claude while following maintain.md - not a hook.

  fold.py list [DIR]        un-folded sessions for the home at or above DIR (default: cwd)
  fold.py read TRANSCRIPT   the user's words, Claude's words and edited file paths
  fold.py done HOME ID@TS.. record those sessions, as `list` printed them, as folded in

`read` never prints tool output or query results (belief 7): only text the user typed,
text Claude wrote, and the paths Claude edited. It exits 1 when it recognizes nothing,
so a changed transcript format stops the fold-in instead of folding an empty session.
"""
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import find_home, load_session, local_time, save_session, unfolded_sessions

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
NOISE_RE = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|command-message|command-name"
    r"|command-args|ide_opened_file|ide_selection)>.*?</\1>|\[Request interrupted by user[^\]]*\]",
    re.S)


def extract(lines):
    """Transcript JSONL lines -> list of (who, text). Skips subagent side chains, meta and
    compaction-summary entries, tool results, and thinking."""
    out = []
    for raw in lines:
        try:
            d = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(d, dict) or d.get("type") not in ("user", "assistant"):
            continue
        if d.get("isSidechain") or d.get("isMeta") or d.get("isCompactSummary"):
            continue
        who = "user" if d["type"] == "user" else "claude"
        content = (d.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                text = NOISE_RE.sub("", b.get("text") or "").strip()
                if text:
                    out.append((who, text))
            elif who == "claude" and b.get("type") == "tool_use" and b.get("name") in EDIT_TOOLS:
                inp = b.get("input") or {}
                path = inp.get("file_path") or inp.get("notebook_path")
                if path and (not out or out[-1] != ("edited", path)):
                    out.append(("edited", path))
    return out


def _home(args):
    home, _ = find_home(Path(args[0] if args else ".").resolve())
    if home is None:
        sys.exit("fold.py: no repo-clean home at or above " + (args[0] if args else "here"))
    return home


def main(argv):
    if not argv or argv[0] not in ("list", "read", "done"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "list":
        home = _home(args)
        sessions = unfolded_sessions(home)
        print(f"{home}: {len(sessions)} un-folded session(s)")
        for s in sessions:
            t = s.get("transcript")
            gone = "" if t and Path(t).exists() else "  (transcript gone - detail lost)"
            print(f"{local_time(s['last_stop'])}  {s['id']}  {t}{gone}")
        if sessions:
            pairs = " ".join(f"{s['id']}@{s['last_stop']!r}" for s in sessions)
            print(f'When finished, run: python "{Path(__file__).resolve()}" done "{home}" {pairs}')
        return 0
    if cmd == "done":
        home = _home(args[:1])
        for pair in args[1:]:
            sid, _, ts = pair.rpartition("@")
            rec = load_session(home, sid)
            if not sid or not rec:
                sys.exit(f"fold.py done: no record for {pair!r}")
            rec["folded_stop"] = float(ts)
            save_session(home, sid, rec)
        # shortcut: needs CLAUDE_CODE_SESSION_ID (set for shell commands); without it this
        # session comes back as waiting (DEF-33), but nothing is lost.
        me = os.environ.get("CLAUDE_CODE_SESSION_ID")
        if me:
            rec = load_session(home, me)
            rec["fold_pending"] = True
            save_session(home, me, rec)
        return 0
    if not args or not Path(args[0]).exists():
        print("fold.py read: transcript not found - record that the session happened and "
              "its detail was lost", file=sys.stderr)
        return 1
    with open(args[0], encoding="utf-8", errors="replace") as f:
        items = extract(f)
    if not items:
        print("fold.py read: recognized nothing in this transcript; stop and tell the user "
              "rather than folding an empty session", file=sys.stderr)
        return 1
    for who, text in items:
        print(f"[{who}] {text}\n")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
