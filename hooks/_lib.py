"""Shared helpers for repo-clean's SessionStart/PostToolUse/Stop/PreCompact hooks.
Stdlib only. Session state lives outside the repo (per-session, keyed by session_id)
so it works the same whether or not the repo has git.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

BASE_DIR = Path(os.environ.get("REPO_CLEAN_HOME") or (Path.home() / ".claude" / "repo-clean"))
DATA_DIR = BASE_DIR / "sessions"


def normalize_cwd(cwd):
    return os.path.normcase(os.path.realpath(str(cwd)))


def read_stdin_json():
    """Malformed or empty stdin is never a reason to block or crash - treat it as no
    data (missing session_id/cwd/tool_input), same as a payload without those keys."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
    except Exception:
        return {}
    # ponytail: capture switch = a directory that exists. mkdir ~/.claude/repo-clean/capture
    # and every hook payload lands there as <event>-<ms>.json; rmdir to stop. No env var,
    # so it takes effect mid-session without restarting Claude Code.
    cap = BASE_DIR / "capture"
    if cap.is_dir():
        try:
            (cap / f"{data.get('hook_event_name', 'unknown')}-{int(time.time()*1000)}.json").write_text(raw, encoding="utf-8")
        except Exception:
            pass
    return data

HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?: \((\d+)\))? [—-] .+$", re.M)
STATE_RE = re.compile(r"^State:\s*(.*)$")


def _session_file(session_id):
    return DATA_DIR / f"{session_id}.json"


def load_session(session_id):
    f = _session_file(session_id)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_session(session_id, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _session_file(session_id).write_text(json.dumps(data), encoding="utf-8")


def add_file(session_id, file_path, cwd=None):
    # ponytail: hardcoded default log dir, not read from a repo's check_docs_local.py
    # CONFIG override - hooks don't load that config. Without this, ensure_entry's own
    # write to docs/log/*.md gets recorded as a "changed file", which the next Stop
    # folds into the same entry's Docs: line, which is itself a file change... a
    # self-feeding loop that never needs a real edit to keep triggering.
    if file_path.startswith("docs/log/"):
        return
    session = load_session(session_id)
    files = session.get("files", [])
    if file_path not in files:
        files.append(file_path)
    session["files"] = files
    if cwd is not None:
        session["cwd"] = normalize_cwd(cwd)
    save_session(session_id, session)


def checker_path(root):
    for rel in ("scripts/tools/check_docs.py", "skills/repo-clean/scripts/check_docs.py"):
        p = root / rel
        if p.exists():
            return p
    return None


def run_checker(root):
    """Returns (returncode, stdout) or None if no checker is installed here."""
    p = checker_path(root)
    if p is None:
        return None
    out = subprocess.run(
        [sys.executable, str(p), "--root", str(root)],
        capture_output=True, text=True, encoding="utf-8",
    )
    return out.returncode, out.stdout


def latest_log_file(root):
    log_dir = root / "docs" / "log"
    if not log_dir.exists():
        return None
    files = sorted(log_dir.glob("*.md"))
    return files[-1] if files else None


FIELD_START_RE = re.compile(r"^[A-Z][\w-]*:")


def _field_span(lines, i):
    """Index range [i, j) covered by the field starting at lines[i], including any
    wrapped continuation lines - a continuation is a non-blank line that doesn't itself
    start a field or a heading."""
    j = i + 1
    while j < len(lines):
        cont = lines[j]
        if not cont.strip() or FIELD_START_RE.match(cont) or cont.startswith("#"):
            break
        j += 1
    return i, j


def last_state_line(root):
    """The last State: field, joined with any wrapped continuation lines."""
    log = latest_log_file(root)
    if log is None:
        return None
    state = None
    for log_file in sorted((root / "docs" / "log").glob("*.md")):
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if not STATE_RE.match(line):
                continue
            start, end = _field_span(lines, i)
            state = " ".join(lines[start:end])
    return state


def _strip_last_state(lines):
    """Remove the last State: field and all of its wrapped continuation lines - leaving
    only the first line behind orphans prose with no State: prefix in the entry body."""
    for i in range(len(lines) - 1, -1, -1):
        if STATE_RE.match(lines[i]):
            start, end = _field_span(lines, i)
            del lines[start:end]
            break
    return lines


def _merge_docs_line(lines, heading, files):
    try:
        start = lines.index(heading)
    except ValueError:
        return lines
    for i in range(start, len(lines)):
        if lines[i].startswith("Docs:"):
            existing = [f.strip() for f in lines[i][len("Docs:"):].split(",") if f.strip()]
            lines[i] = "Docs: " + ", ".join(sorted(set(existing) | set(files)))
            return lines
    return lines


def _heading_key_re(date_str, n):
    """Matches this entry's heading line regardless of its (agent-edited) headline text
    - only the date+N portion identifies which entry belongs to this session."""
    suffix = re.escape(f" ({n})") if n else ""
    return re.compile(rf"^## {re.escape(date_str)}{suffix} [—-] .+$", re.M)


def _find_heading_line(lines, date_str, n):
    pat = _heading_key_re(date_str, n)
    for line in lines:
        if pat.match(line):
            return line
    return None


def ensure_entry(root, session, files):
    """Create this session's log entry (first call) or fold new files into its Docs:
    line (later calls). Mutates `session` in place with the date/N it used - not the
    heading text itself, which the agent is expected to edit away from "TBD". Returns
    the log Path, or None if there's no docs/log dir to write into.

    ponytail: Docs: merge assumes a single-line field (no wrap-aware re-merge); the
    diary-grammar/log-fields-resolve rules don't require wrapping, just a real path.
    """
    log = latest_log_file(root)
    if log is None:
        return None
    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    today = date.today().isoformat()

    entry_date, entry_n = session.get("entry_date"), session.get("entry_n")
    heading = _find_heading_line(lines, entry_date, entry_n) if entry_date else None
    if heading:
        lines = _merge_docs_line(lines, heading, files)
    else:
        same_date = sum(1 for m in HEADING_RE.finditer(text) if m.group(1) == today)
        n = same_date + 1 if same_date else None
        heading = f"## {today}" + (f" ({n})" if n else "") + " — TBD"
        lines = _strip_last_state(lines)
        if lines and lines[-1].strip():
            lines.append("")
        lines += [heading, "", "Decisions: none", "Docs: " + ", ".join(sorted(set(files))),
                  "State: TBD", ""]
        session["entry_date"], session["entry_n"] = today, n

    log.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return log


def _current_heading(log, session):
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return _find_heading_line(lines, session.get("entry_date"), session.get("entry_n"))


def entry_line_no(log, session):
    heading = _current_heading(log, session)
    if heading is None:
        return "?"
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines.index(heading) + 1


OFFERED_FILE = BASE_DIR / "offered.json"
ORPHAN_AGE_SECONDS = 2 * 3600
PRUNE_AGE_SECONDS = 7 * 24 * 3600


def setup_already_offered(cwd):
    """True if the setup nag has already fired for this cwd; records it either way."""
    norm = normalize_cwd(cwd)
    try:
        offered = json.loads(OFFERED_FILE.read_text(encoding="utf-8"))
    except Exception:
        offered = {}
    seen = norm in offered
    if not seen:
        offered[norm] = True
        OFFERED_FILE.parent.mkdir(parents=True, exist_ok=True)
        OFFERED_FILE.write_text(json.dumps(offered), encoding="utf-8")
    return seen


def carry_over_orphans(session_id, cwd):
    """One pass over DATA_DIR: merge stale same-cwd orphans into this session, prune
    anything old regardless of cwd. Returns the number of files carried over."""
    norm = normalize_cwd(cwd)
    this_file = _session_file(session_id)
    now = time.time()
    carried = 0
    if not DATA_DIR.exists():
        return 0
    for f in DATA_DIR.glob("*.json"):
        if f == this_file:
            continue
        try:
            age = now - f.stat().st_mtime
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        is_orphan_candidate = data.get("files") or data.get("pending")
        if data.get("cwd") == norm and is_orphan_candidate and age > ORPHAN_AGE_SECONDS:
            session = load_session(session_id)
            files = session.get("files", [])
            for fp in data.get("files", []):
                if fp not in files:
                    files.append(fp)
            session["files"] = files
            session["cwd"] = norm
            save_session(session_id, session)
            carried += len(data.get("files", []))
            f.unlink()
        elif age > PRUNE_AGE_SECONDS:
            f.unlink()
    return carried


def entry_has_placeholder(log, session):
    """True if this session's entry still has its headline or State: unfilled."""
    text = log.read_text(encoding="utf-8", errors="replace")
    heading = _current_heading(log, session)
    if heading is None:
        return False
    idx = text.find(heading)
    entry = text[idx:]
    next_heading = re.search(r"\n## \d{4}-\d{2}-\d{2}", entry[1:])
    if next_heading:
        entry = entry[: next_heading.start() + 1]
    # Only the two placeholder lines count. The body may legitimately mention "TBD"
    # (e.g. an entry describing this very hook) - found live on 2026-09-19.
    if heading.rstrip().endswith("— TBD"):
        return True
    return any(STATE_RE.match(line) and line.split(":", 1)[1].strip() == "TBD"
               for line in entry.splitlines())
