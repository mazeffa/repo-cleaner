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
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(os.environ.get("REPO_CLEAN_HOME") or (Path.home() / ".claude" / "repo-clean"))
HOMES_DIR = BASE_DIR / "homes"
PLUGIN_ROOT = Path(__file__).resolve().parents[1]
# Every hook imports this module, so every hook can `import check_docs` (D-022: the plugin's
# own checker, never a copy found in a project). Outside any try, so a bad path is loud.
sys.path.insert(0, str(PLUGIN_ROOT / "skills" / "repo-clean" / "scripts"))


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
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")  # replace, so a crash never leaves half a record; pid, so two windows don't share one
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, f)


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
    rec.setdefault("checked_at", time.time())  # from here on, Stop also catches changes made by any means
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
    """Walk up from cwd to the nearest folder with the `.repo-clean` marker (D-023), or None."""
    p = Path(cwd).resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".repo-clean").exists():
            return candidate
    return None


def find_homes_nearby(cwd, depth=2):
    """Homes up to `depth` levels below cwd, for a session opened above them. Not a general
    scan - D-018 only globs two levels down from where the session already is."""
    p = Path(cwd)
    found = set()
    for level in range(1, depth + 1):
        found.update(m.parent for m in p.glob("/".join(["*"] * level) + "/.repo-clean"))
    return sorted(found)


def checker_path():
    """Always the checker shipped beside these hooks (D-022) - never a project's own copy and
    never another version found in the plugin cache."""
    return PLUGIN_ROOT / "skills" / "repo-clean" / "scripts" / "check_docs.py"


def run_checker(root, timeout=25):
    """Always (returncode, text): 0 clean, 1 doc findings, 2 the checker itself failed or is
    missing, 124 it timed out. Only 1 is a finding about the docs. The hook limit is 30 s."""
    p = checker_path()
    if not p.exists():
        return 2, f"checker not found: {p}"
    try:
        out = subprocess.run(
            [sys.executable, str(p), "--root", str(root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "checker timed out"
    # A real finding always prints to stdout; exit 1 with none is a traceback, i.e. a crash.
    code = out.returncode if out.returncode == 0 or (out.returncode == 1 and out.stdout.strip()) else 2
    return code, out.stdout or out.stderr


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
