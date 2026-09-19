#!/usr/bin/env python3
"""Self-test for hooks/. Stdlib only. `python hooks/selftest.py` exits 0 or asserts.

Drives each hook via subprocess against a scratch copy of this repo (a known-good doc
tree), under a temp dir whose path has both a non-ASCII char and a space, so path
handling bugs surface here instead of in a real session. Session/offer state is
isolated per test via REPO_CLEAN_HOME so this never touches a real user's data.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
FIXTURES_DIR = HOOKS_DIR / "fixtures"

_FAILURES = []


def check(label, cond, detail=""):
    if not cond:
        _FAILURES.append(f"{label}: {detail}")
        print(f"FAIL: {label} {detail}", file=sys.stderr)
    else:
        print(f"ok: {label}")


_scratch_n = [0]


def make_scratch_repo(base):
    _scratch_n[0] += 1
    dest = base / f"réviser projet {_scratch_n[0]}"  # non-ASCII + space
    shutil.copytree(
        REPO_ROOT, dest,
        ignore=shutil.ignore_patterns(".git", "__pycache__"),
    )
    return dest


EVENT_OF = {"post_tool_use.py": "PostToolUse", "stop.py": "Stop",
            "pre_compact.py": "PreCompact", "session_start.py": "SessionStart"}


def payload(name, fields):
    """Test fields overlaid on the real payload captured from a live Claude Code session
    (hooks/fixtures/<Event>.json), so every assertion runs against the real key set."""
    f = FIXTURES_DIR / f"{EVENT_OF.get(name, '')}.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    data.update(fields)
    return data


def run_hook(name, data, home, input_text=None):
    env = dict(os.environ)
    env["REPO_CLEAN_HOME"] = str(home)
    env["PYTHONIOENCODING"] = "utf-8"
    stdin = input_text if input_text is not None else json.dumps(payload(name, data))
    out = subprocess.run(
        [sys.executable, str(HOOKS_DIR / name)],
        input=stdin, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return out.returncode, out.stdout, out.stderr


def session_file(home, session_id):
    return home / "sessions" / f"{session_id}.json"


def load_session(home, session_id):
    f = session_file(home, session_id)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def write_session(home, session_id, data):
    d = home / "sessions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_id}.json").write_text(json.dumps(data), encoding="utf-8")


def log_path(repo):
    return sorted((repo / "docs" / "log").glob("*.md"))[-1]


def test_post_tool_use(base):
    repo = make_scratch_repo(base)
    home = base / "home1"
    sid = "s1"

    rc, _, _ = run_hook("post_tool_use.py",
                         {"session_id": sid, "cwd": str(repo),
                          "tool_input": {"file_path": str(repo / "README.md")}}, home)
    check("post_tool_use: exit 0", rc == 0)
    sess = load_session(home, sid)
    check("post_tool_use: records a file", sess and sess["files"] == ["README.md"], sess)
    check("post_tool_use: stores normalized cwd",
          sess and sess["cwd"] == os.path.normcase(os.path.realpath(str(repo))), sess)

    run_hook("post_tool_use.py",
              {"session_id": sid, "cwd": str(repo),
               "tool_input": {"file_path": str(repo / "docs" / "log" / log_path(repo).name)}},
              home)
    sess = load_session(home, sid)
    check("post_tool_use: ignores docs/log/", sess["files"] == ["README.md"], sess)

    run_hook("post_tool_use.py",
              {"session_id": sid, "cwd": str(repo),
               "tool_input": {"file_path": str(repo / "README.md")}}, home)
    sess = load_session(home, sid)
    check("post_tool_use: dedups", sess["files"] == ["README.md"], sess)


def test_stop(base):
    repo = make_scratch_repo(base)
    home = base / "home2"

    rc, out, err = run_hook("stop.py", {"session_id": "nosuch", "cwd": str(repo)}, home)
    check("stop: silent, no session record", rc == 0 and not out and not err)

    write_session(home, "clean", {"files": [], "pending": False})
    rc, out, err = run_hook("stop.py", {"session_id": "clean", "cwd": str(repo)}, home)
    check("stop: silent when nothing changed", rc == 0 and not out and not err)

    write_session(home, "s3", {"files": ["README.md"], "pending": False})
    rc, out, err = run_hook("stop.py", {"session_id": "s3", "cwd": str(repo)}, home)
    check("stop: blocks with TBD", rc == 2)
    check("stop: reason on stderr", "not ready" in err)
    check("stop: nothing on stdout", out == "")

    log = log_path(repo)
    text = log.read_text(encoding="utf-8")
    text = text.replace("— TBD", "— fixed the thing")
    text = text.rsplit("State: TBD", 1)
    text = "State: it works.".join(text)
    # body text may mention TBD without being a placeholder (found live 2026-09-19)
    text = text.replace("State: it works.", "Replaced the TBD placeholders.\nState: it works.")
    log.write_text(text, encoding="utf-8")
    rc, out, err = run_hook("stop.py", {"session_id": "s3", "cwd": str(repo)}, home)
    check("stop: passes after headline+State filled", rc == 0, err)

    (repo / "second.md").write_text("x\n", encoding="utf-8")
    run_hook("post_tool_use.py",
              {"session_id": "s3", "cwd": str(repo),
               "tool_input": {"file_path": str(repo / "second.md")}}, home)
    rc, out, err = run_hook("stop.py", {"session_id": "s3", "cwd": str(repo)}, home)
    new_text = log.read_text(encoding="utf-8")
    check("stop: second edit merges Docs:, no second heading",
          new_text.count("— fixed the thing") == 1 and "second.md" in new_text, rc)

    write_session(home, "s4", {"files": ["README.md"], "pending": False})
    for i in range(3):
        rc, out, err = run_hook("stop.py", {"session_id": "s4", "cwd": str(repo)}, home)
        check(f"stop: retry {i+1} blocks", rc == 2, err)
    rc, out, err = run_hook("stop.py", {"session_id": "s4", "cwd": str(repo)}, home)
    check("stop: gives up after MAX_RETRIES", rc == 0)
    check("stop: giving-up text names unverified", "entry passed unverified" in err, err)


def test_stop_wrapped_state(base):
    repo = make_scratch_repo(base)
    home = base / "home_wrap"
    log = log_path(repo)
    today = __import__("datetime").date.today().isoformat()
    log.write_text(
        log.read_text(encoding="utf-8").rstrip("\n") + "\n\n"
        f"## {today} — earlier entry\n\nDecisions: none\nDocs: README.md\n"
        "State: line one\nwraps onto a second line here.\n",
        encoding="utf-8",
    )
    write_session(home, "wrap-sess", {"files": ["README.md"], "pending": False})
    run_hook("stop.py", {"session_id": "wrap-sess", "cwd": str(repo)}, home)
    text = log.read_text(encoding="utf-8")
    check("stop: wrapped State: removed whole, no orphan continuation",
          "wraps onto a second line here." not in text, text[-400:])


def test_precompact(base):
    repo = make_scratch_repo(base)
    home = base / "home3"
    write_session(home, "p1", {"files": ["README.md"]})
    rc, out, err = run_hook("pre_compact.py", {"session_id": "p1", "cwd": str(repo)}, home)
    check("precompact: exit 0", rc == 0)
    sess = load_session(home, "p1")
    check("precompact: pending true", sess["pending"] is True, sess)
    text = log_path(repo).read_text(encoding="utf-8")
    check("precompact: creates entry", "Docs: README.md" in text, text[-200:])

    (repo / "second.md").write_text("x\n", encoding="utf-8")
    sess["files"] = ["second.md"]
    write_session(home, "p1", sess)
    run_hook("pre_compact.py", {"session_id": "p1", "cwd": str(repo)}, home)
    text = log_path(repo).read_text(encoding="utf-8")
    check("precompact: merges into existing today entry, no new heading",
          text.count("— TBD") == 1 and "second.md" in text)


def test_session_start(base):
    repo = make_scratch_repo(base)
    home = base / "home4"

    rc, out, err = run_hook("session_start.py", {"session_id": "a1", "cwd": str(repo)}, home)
    from _lib import last_state_line  # noqa: reuse the real helper to compute expectation
    check("session_start: prints State:", out.strip() == last_state_line(repo), out)

    no_setup_home = base / "home5"
    unset_repo = base / "réviser projet sans config"
    shutil.copytree(repo, unset_repo)
    (unset_repo / "CLAUDE.md").unlink()
    rc, out1, _ = run_hook("session_start.py", {"session_id": "b1", "cwd": str(unset_repo)},
                            no_setup_home)
    rc, out2, _ = run_hook("session_start.py", {"session_id": "b2", "cwd": str(unset_repo)},
                            no_setup_home)
    check("session_start: setup offer fires once", "init" in out1)
    check("session_start: setup offer silent second time", out2.strip() == "", out2)

    orphan_home = base / "home6"
    from _lib import normalize_cwd
    norm = normalize_cwd(repo)
    now = time.time()

    write_session(orphan_home, "old_same_cwd", {"files": ["orphan.py"], "cwd": norm})
    os.utime(session_file(orphan_home, "old_same_cwd"), (now - 3 * 3600, now - 3 * 3600))

    other_repo = base / "other"
    other_repo.mkdir()
    write_session(orphan_home, "old_other_cwd",
                  {"files": ["x.py"], "cwd": normalize_cwd(other_repo)})
    os.utime(session_file(orphan_home, "old_other_cwd"), (now - 3 * 3600, now - 3 * 3600))

    write_session(orphan_home, "recent_same_cwd", {"files": ["recent.py"], "cwd": norm})
    os.utime(session_file(orphan_home, "recent_same_cwd"), (now - 600, now - 600))

    write_session(orphan_home, "ancient", {"files": ["a.py"], "cwd": normalize_cwd(other_repo)})
    os.utime(session_file(orphan_home, "ancient"), (now - 8 * 24 * 3600, now - 8 * 24 * 3600))

    write_session(orphan_home, "day_old", {"files": ["b.py"], "cwd": normalize_cwd(other_repo)})
    os.utime(session_file(orphan_home, "day_old"), (now - 1 * 24 * 3600, now - 1 * 24 * 3600))

    rc, out, err = run_hook("session_start.py", {"session_id": "current", "cwd": str(repo)},
                             orphan_home)
    cur = load_session(orphan_home, "current")
    check("session_start: orphan same cwd >2h merged", "orphan.py" in (cur or {}).get("files", []))
    check("session_start: orphan same cwd >2h file removed",
          not session_file(orphan_home, "old_same_cwd").exists())
    check("session_start: orphan different cwd untouched",
          session_file(orphan_home, "old_other_cwd").exists())
    check("session_start: 10-min-old same-cwd session untouched",
          session_file(orphan_home, "recent_same_cwd").exists())
    check("session_start: 8-day-old file pruned",
          not session_file(orphan_home, "ancient").exists())
    check("session_start: 1-day-old file kept",
          session_file(orphan_home, "day_old").exists())
    check("session_start: carryover message printed", "Carried" in out, out)


def test_bad_input(base):
    repo = make_scratch_repo(base)
    home = base / "home_bad"
    for hook in ("post_tool_use.py", "stop.py", "pre_compact.py", "session_start.py"):
        rc, out, err = run_hook(hook, None, home, input_text="")
        check(f"{hook}: empty stdin exits 0", rc == 0, (out, err))
        rc, out, err = run_hook(hook, None, home, input_text="not json{{{")
        check(f"{hook}: non-JSON stdin exits 0", rc == 0, (out, err))
        rc, out, err = run_hook(hook, None, home, input_text=json.dumps({"foo": "bar"}))
        check(f"{hook}: missing keys exits 0", rc == 0, (out, err))


def test_pre_commit(base):
    repo = make_scratch_repo(base)
    sh = shutil.which("sh") or shutil.which("bash")
    if sh is None:
        print("skip: pre-commit test (no sh/bash on PATH)")
        return
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "docs" / "bad.md").write_text("# bad\n## TODO\nnope\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    out = subprocess.run([sh, str(repo / "scripts" / "hooks" / "pre-commit")],
                          cwd=repo, capture_output=True, text=True, encoding="utf-8", env=env)
    check("pre-commit: exits non-zero on banned header", out.returncode != 0, out.stdout + out.stderr)


def main():
    with tempfile.TemporaryDirectory(prefix="repo_clean_selftest_") as tmp:
        base = Path(tmp)
        test_post_tool_use(base)
        test_stop(base)
        test_stop_wrapped_state(base)
        test_precompact(base)
        test_session_start(base)
        test_bad_input(base)
        test_pre_commit(base)

    if _FAILURES:
        print(f"\n{len(_FAILURES)} failure(s):", file=sys.stderr)
        for f in _FAILURES:
            print(f" - {f}", file=sys.stderr)
        return 1
    print("\nselftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
