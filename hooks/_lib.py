"""Shared helpers for repo-clean's SessionStart hook. Stdlib only. The only state outside
the repo is offered.json: the folders already offered setup, so the offer fires once.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(os.environ.get("REPO_CLEAN_HOME") or (Path.home() / ".claude" / "repo-clean"))
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def normalize_cwd(cwd):
    return os.path.normcase(os.path.realpath(str(cwd)))


def read_stdin_json():
    """Malformed or empty stdin is never a reason to crash - treat it as no data, same as a
    payload without the keys."""
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


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


def find_home(cwd):
    """Walk up from cwd to the nearest folder with the `.repo-clean` marker (D-023), or None."""
    p = Path(cwd).resolve()
    for candidate in (p, *p.parents):
        if (candidate / ".repo-clean").exists():
            return candidate
    return None


def find_homes_nearby(cwd, depth=2):
    """Homes up to `depth` levels below cwd, for a session opened above them. Not a general
    scan - D-023 only globs two levels down from where the session already is."""
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
    """Run `check_docs.py --summary` once. Always (returncode, text): 0 clean, 1 doc findings,
    2 the checker itself failed or is missing, 124 it timed out (text is what it printed
    before that - the summary comes first). Only 1 is a finding about the docs. The hook
    limit is 30 s."""
    p = checker_path()
    if not p.exists():
        return 2, f"checker not found: {p}"
    try:
        out = subprocess.run(
            [sys.executable, str(p), "--root", str(root), "--summary"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or ""
        return 124, partial.decode("utf-8", "replace") if isinstance(partial, bytes) else partial
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
        try:
            _write_json(OFFERED_FILE, offered)
        except OSError:  # an unwritable state dir only means the offer may repeat
            pass
    return seen
