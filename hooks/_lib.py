"""Shared helpers for repo-clean's SessionStart/PostToolUse/Stop/PreCompact hooks.
Stdlib only. Session state lives outside the repo (per-session, keyed by session_id)
so it works the same whether or not the repo has git.
"""
import json
import re
import subprocess
from datetime import date
from pathlib import Path

DATA_DIR = Path.home() / ".claude" / "repo-clean" / "sessions"

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


def add_file(session_id, file_path):
    session = load_session(session_id)
    files = session.get("files", [])
    if file_path not in files:
        files.append(file_path)
    session["files"] = files
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
        ["python", str(p), "--root", str(root)],
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
            parts = [line]
            for cont in lines[i + 1:]:
                if not cont.strip() or FIELD_START_RE.match(cont) or cont.startswith("#"):
                    break
                parts.append(cont)
            state = " ".join(parts)
    return state


def _strip_last_state(lines):
    for i in range(len(lines) - 1, -1, -1):
        if STATE_RE.match(lines[i]):
            del lines[i]
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
    return "TBD" in entry
