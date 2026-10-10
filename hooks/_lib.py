"""Shared helpers for repo-clean's SessionStart/PostToolUse/Stop hooks and fold.py.
Stdlib only. State lives outside the repo, so it works the same with or without git.

The registry (D-021): one record per (home, session) under BASE_DIR/homes/<key>/, plus
the last Stop it has had folded in ("folded_stop"). A record is un-folded while its
"last_stop" is past "folded_stop". No age prune - a record stays until a fold-in has
covered it, however long that takes.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(os.environ.get("REPO_CLEAN_HOME") or (Path.home() / ".claude" / "repo-clean"))
HOMES_DIR = BASE_DIR / "homes"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def normalize_cwd(cwd):
    return os.path.normcase(os.path.realpath(str(cwd)))


def read_stdin_json():
    """Malformed or empty stdin is never a reason to block or crash - treat it as no
    data (missing session_id/cwd/tool_input), same as a payload without those keys."""
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


STATE_RE = re.compile(r"^State:\s*(.*)$")
NEXT_RE = re.compile(r"^Next:\s*(.*)$")


def local_time(ts):
    return datetime.fromtimestamp(ts).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _home_dir(home):
    return HOMES_DIR / hashlib.sha1(normalize_cwd(home).encode("utf-8")).hexdigest()[:16]


def _read_json(f):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(f, data):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data), encoding="utf-8")


def load_session(home, session_id):
    return _read_json(_home_dir(home) / f"{session_id}.json")


def save_session(home, session_id, data):
    data["home"] = str(home)
    _write_json(_home_dir(home) / f"{session_id}.json", data)


def session_homes(session_id):
    """Every home this session has a record in, as (home, record) pairs."""
    if not HOMES_DIR.is_dir():
        return []
    out = []
    for f in sorted(HOMES_DIR.glob(f"*/{session_id}.json")):
        rec = _read_json(f)
        if rec.get("home"):
            out.append((Path(rec["home"]), rec))
    return out


def add_file(session_id, home, rel_path):
    rec = load_session(home, session_id)
    if rel_path.lower().endswith(".md"):
        rec["dirty"] = True  # a doc changed; the next Stop runs the checker for this home
    save_session(home, session_id, rec)


def unfolded_sessions(home):
    """Records for this home whose last Stop is past their last folded one, oldest first.
    Each is the record dict plus its session id under "id"."""
    d = _home_dir(home)
    if not d.is_dir():
        return []
    out = []
    for f in d.glob("*.json"):
        rec = _read_json(f)
        if rec.get("last_stop", 0) > rec.get("folded_stop", 0):
            out.append(dict(rec, id=f.stem))
    return sorted(out, key=lambda r: r["last_stop"])


def find_home(cwd):
    """Walk up from cwd to the nearest repo-clean home (D-018). A home is either a
    folder with the `.repo-clean` marker, or - for an install from before the marker
    existed - a folder with `CLAUDE.md` and `docs/log/` and no marker yet (legacy).
    Returns (home_path, is_legacy), or (None, False) if the walk reaches the filesystem
    root with no home found."""
    p = Path(cwd).resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".repo-clean").exists():
            return candidate, False
        if (candidate / "CLAUDE.md").exists() and (candidate / "docs" / "log").is_dir():
            return candidate, True
    return None, False


def find_homes_nearby(cwd, depth=2):
    """Homes up to `depth` levels below cwd - markers, and pre-marker homes (CLAUDE.md
    beside docs/log/) - for a session opened above them. Not a general scan - D-018 only
    globs two levels down from where the session already is."""
    p = Path(cwd)
    found = set()
    for level in range(1, depth + 1):
        stars = "/".join(["*"] * level)
        found.update(m.parent for m in p.glob(stars + "/.repo-clean"))
        found.update(m.parent.parent for m in p.glob(stars + "/docs/log")
                     if (m.parent.parent / "CLAUDE.md").exists())
    return sorted(found)


def migrate_already_offered(home):
    """Same one-shot-per-folder gate as setup_already_offered, keyed separately so the
    legacy-migrate hint and the no-doc-system offer don't suppress each other."""
    return setup_already_offered(Path(str(home)) / ".migrate-hint-key")


def checker_path(root):
    """The checker that runs for this home (D-015): its own working-tree copy if root
    IS the plugin's source repo (dogfooding), else the one shipped beside these hooks -
    never another version found in the plugin cache. No copy is vendored into a home."""
    for base in (root, PLUGIN_ROOT):
        p = base / "skills" / "repo-clean" / "scripts" / "check_docs.py"
        if p.exists():
            return p
    return None


def run_checker(root):
    """Returns (returncode, stdout) or None if no checker is installed here."""
    p = checker_path(root)
    if p is None:
        return None
    try:
        out = subprocess.run(
            [sys.executable, str(p), "--root", str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,  # hook limit is 30
        )
    except subprocess.TimeoutExpired:
        return 1, "checker timed out"
    return out.returncode, out.stdout


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


def last_field(root, field_re):
    """The last such field across the log's period files, joined with any wrapped
    continuation lines."""
    log_dir = root / "docs" / "log"
    found = None
    for log_file in sorted(log_dir.glob("*.md")) if log_dir.is_dir() else []:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(lines):
            if field_re.match(line):
                start, end = _field_span(lines, i)
                found = " ".join(lines[start:end])
    return found


def last_state_line(root):
    return last_field(root, STATE_RE)


OFFERED_FILE = BASE_DIR / "offered.json"


def setup_already_offered(cwd):
    """True if the setup nag has already fired for this cwd; records it either way."""
    norm = normalize_cwd(cwd)
    offered = _read_json(OFFERED_FILE)
    seen = norm in offered
    if not seen:
        offered[norm] = True
        _write_json(OFFERED_FILE, offered)
    return seen
