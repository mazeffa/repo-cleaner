#!/usr/bin/env python3
"""Fold-in helper (D-021), run by Claude while following maintain.md - not a hook. Claude only
ever passes the project folder (HOME); no ids or timestamps to copy.

  fold.py list HOME [--check]    the sessions waiting to be folded in; remembers which it showed
  fold.py read HOME [--from N]   what they said and did, oldest session first, in pages
  fold.py done HOME              record the listed sessions as folded in (refuses until read)

`read` never prints tool output (belief 7): only text the user typed, text Claude wrote, the
paths Claude edited, and the answers the user gave to AskUserQuestion/ExitPlanMode. It prints
only what is newer than the session's last fold-in. A transcript that is gone or unreadable is
reported and skipped; `read` exits 1 only when every listed session is. `list --check` writes
nothing, so a `--check` run leaves no trace.
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import find_home, load_session, local_time, save_session, unfolded_sessions

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
ANSWER_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
PAGE_CHARS = 20000
NOISE_RE = re.compile(
    r"<(system-reminder|local-command-stdout|local-command-stderr|command-message|command-name"
    r"|command-args|ide_opened_file|ide_selection)>.*?</\1>|\[Request interrupted by user[^\]]*\]",
    re.S)


def _epoch(ts):
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None  # no usable timestamp: the entry counts as new


def extract(lines):
    """Transcript JSONL lines -> list of (who, text, epoch or None). Skips subagent side
    chains, meta and compaction-summary entries, tool results (except the user's answers to
    AskUserQuestion/ExitPlanMode), and thinking."""
    out = []
    answering = set()  # tool_use ids whose result is the user's own answer
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
        ts = _epoch(d["timestamp"]) if d.get("timestamp") else None
        content = (d.get("message") or {}).get("content")
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text":
                text = NOISE_RE.sub("", b.get("text") or "").strip()
                if text:
                    out.append((who, text, ts))
            elif who == "claude" and b.get("type") == "tool_use":
                if b.get("name") in ANSWER_TOOLS:
                    answering.add(b.get("id"))
                elif b.get("name") in EDIT_TOOLS:
                    inp = b.get("input") or {}
                    path = inp.get("file_path") or inp.get("notebook_path")
                    if path and (not out or out[-1][:2] != ("edited", path)):
                        out.append(("edited", path, ts))
            elif who == "user" and b.get("type") == "tool_result" and b.get("tool_use_id") in answering:
                body = b.get("content")
                if isinstance(body, list):
                    body = "\n".join(x.get("text", "") for x in body if isinstance(x, dict))
                if isinstance(body, str) and body.strip():
                    out.append(("user answer", body.strip(), ts))
    return out


def _home(args):
    path = next((a for a in args if not a.startswith("--")), ".")
    home = find_home(Path(path).resolve())
    if home is None:
        sys.exit("fold.py: no repo-clean home at or above " + path)
    return home


def _session_items(s):
    """The printable blocks for one waiting session, and whether its detail was lost."""
    t = s.get("transcript")
    if not t or not Path(t).exists():
        return [f"[session {s['id']}: transcript gone — detail lost]"], True
    try:
        with open(t, encoding="utf-8", errors="replace") as f:
            items = extract(f)
    except OSError:
        items = []
    if not items:
        return [f"[session {s['id']}: unreadable — detail lost]"], True
    cut = s.get("folded_stop", 0)
    new = [(who, text) for who, text, ts in items if ts is None or ts > cut]
    if not new:
        return [f"[session {s['id']}: nothing new since its last fold-in]"], False
    return [f"[{who}] {text}\n" for who, text in new], False


def cmd_list(home, check):
    sessions = unfolded_sessions(home)
    print(f"{home}: {len(sessions)} un-folded session(s)")
    for s in sessions:
        t = s.get("transcript")
        gone = "" if t and Path(t).exists() else "  (transcript gone - detail lost)"
        print(f"{local_time(s['last_stop'])}  {s['id']}  {t}{gone}")
        if not check:
            rec = load_session(home, s["id"])
            rec["listed_stop"] = s["last_stop"]
            rec.pop("read_complete", None)
            save_session(home, s["id"], rec)
    if sessions:
        print(f'Read them with: python "{Path(__file__).resolve()}" read "{home}"')
    return 0


def cmd_read(home, start):
    waiting = unfolded_sessions(home)
    sessions = [s for s in waiting if "listed_stop" in s]
    staged = bool(sessions)
    if not staged:
        sessions = waiting  # `list --check` left nothing staged: read, record nothing
    if not sessions:
        print("fold.py read: no un-folded sessions")
        return 0
    flat, spans, lost = [], {}, {}  # item list, id -> (first, last) index, id -> detail lost
    for s in sessions:
        items, lost[s["id"]] = _session_items(s)
        spans[s["id"]] = (len(flat), len(flat) + len(items) - 1)
        flat.extend((s["id"], text) for text in items)
    if start >= len(flat):
        sys.exit(f"fold.py read: --from {start} is past the last item ({len(flat)})")
    end, size, shown = start, 0, None
    while end < len(flat) and (end == start or size < PAGE_CHARS):
        sid, text = flat[end]
        if sid != shown:
            print(f"=== session {sid} ===\n")
            shown = sid
        print(text if text.endswith("\n") else text + "\n")
        size += len(text)
        end += 1
    if staged:
        for sid, (_, last) in spans.items():
            if start <= last < end:  # its last item went out on this page
                rec = load_session(home, sid)
                rec["read_complete"] = True
                save_session(home, sid, rec)
    if end < len(flat):
        print(f'-- more: items {end}..{len(flat) - 1} of {len(flat)}; '
              f'run: python "{Path(__file__).resolve()}" read "{home}" --from {end}')
    return 1 if all(lost.values()) else 0


def cmd_done(home):
    listed = [s for s in unfolded_sessions(home) if "listed_stop" in s]
    unread = [s["id"] for s in listed if not s.get("read_complete")]
    if unread:
        print("fold.py done: refusing - not read to the end yet: " + ", ".join(unread) +
              f'. Run `read "{home}"` (with --from N for later pages) until no "more" line.',
              file=sys.stderr)
        return 1
    for s in listed:
        rec = load_session(home, s["id"])
        rec["folded_stop"] = rec.pop("listed_stop")
        rec.pop("read_complete", None)
        save_session(home, s["id"], rec)
    # shortcut: needs CLAUDE_CODE_SESSION_ID (set for shell commands); without it this
    # session comes back as waiting (DEF-33), but nothing is lost.
    me = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if me:
        rec = load_session(home, me)
        rec["fold_pending"] = True
        save_session(home, me, rec)
    return 0


def main(argv):
    if not argv or argv[0] not in ("list", "read", "done"):
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    home = _home(args)
    if cmd == "list":
        return cmd_list(home, "--check" in args)
    if cmd == "done":
        return cmd_done(home)
    start = int(args[args.index("--from") + 1]) if "--from" in args else 0
    return cmd_read(home, start)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
