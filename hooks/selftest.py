#!/usr/bin/env python3
"""Self-test for hooks/. Stdlib only. `python hooks/selftest.py` exits 0 or asserts.
Run by hand; nothing runs it automatically (D-021).

Drives each hook via subprocess against a scratch copy of this repo (a known-good doc
tree), under a temp dir whose path has both a non-ASCII char and a space, so path
handling bugs surface here instead of in a real session. Registry/offer state is
isolated per test via REPO_CLEAN_HOME so this never touches a real user's data.
Also holds the checker's rule tests (test_checker_rules) - the one test command.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
FIXTURES_DIR = HOOKS_DIR / "fixtures"
sys.path.insert(0, str(HOOKS_DIR))
import _lib  # noqa: E402,F401  - its path insert is how the hooks (and these tests) import check_docs
import check_docs  # noqa: E402

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


def make_home(parent, name, broken=False):
    """A small marked home with a clean doc set - or, with broken=True, a dangling link."""
    h = parent / name
    (h / "docs" / "log").mkdir(parents=True)
    (h / ".repo-clean").write_text("", encoding="utf-8")
    (h / "CLAUDE.md").write_text(
        "| Q | A |\n|---|---|\n| decisions | `docs/DECISIONS.md` |\n", encoding="utf-8")
    (h / "README.md").write_text(
        "See `docs/NOT_THERE.md`.\n" if broken else "fine\n", encoding="utf-8")
    (h / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n## Fields\n\n## D-001 — a\nStatus: active   Verdict: adopted\n",
        encoding="utf-8")
    (h / "docs" / "log" / "2026.md").write_text(
        "## 2026-01-01 — start\n\nDecisions: D-001\nDocs: CLAUDE.md\nState: ok → next\nNext: more\n",
        encoding="utf-8")
    return h


EVENT_OF = {"post_tool_use.py": "PostToolUse", "stop.py": "Stop",
            "session_start.py": "SessionStart"}


def payload(name, fields):
    """Test fields overlaid on the real payload captured from a live Claude Code session
    (hooks/fixtures/<Event>.json), so every assertion runs against the real key set."""
    f = FIXTURES_DIR / f"{EVENT_OF.get(name, '')}.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    data.update(fields)
    return data


def run_hook(name, data, home, input_text=None, extra_env=None, args=(), hooks_dir=None):
    env = dict(os.environ)
    env["REPO_CLEAN_HOME"] = str(home)
    env.pop("CLAUDE_CODE_SESSION_ID", None)  # this session's own id must not leak in
    if extra_env:
        env.update(extra_env)
    stdin = input_text if input_text is not None else json.dumps(payload(name, data or {}))
    out = subprocess.run(
        [sys.executable, str((hooks_dir or HOOKS_DIR) / name), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return out.returncode, out.stdout, out.stderr


def records(state, session_id):
    """{home folder name: record} for every home this session has a record in."""
    out = {}
    for f in (state / "homes").glob(f"*/{session_id}.json"):
        rec = json.loads(f.read_text(encoding="utf-8"))
        out[Path(rec["home"]).name] = rec
    return out


def edit(state, sid, cwd, path, hooks_dir=None):
    run_hook("post_tool_use.py", {"session_id": sid, "cwd": str(cwd),
                                  "tool_input": {"file_path": str(path)}}, state,
             hooks_dir=hooks_dir)


def stop(state, sid, cwd, active=False, transcript=None, hooks_dir=None):
    # a transcript that does not exist, unless a test supplies one: the fixture's own path
    # may exist on the machine running this
    return run_hook("stop.py", {"session_id": sid, "cwd": str(cwd), "stop_hook_active": active,
                                "transcript_path": str(transcript or state / "gone.jsonl")},
                    state, hooks_dir=hooks_dir)


def record_file(state, sid, name):
    for f in (state / "homes").glob(f"*/{sid}.json"):
        if Path(json.loads(f.read_text(encoding="utf-8"))["home"]).name == name:
            return f


def patch_record(state, sid, name, **fields):
    """Set (or, for None, remove) fields on this session's record for the home `name`."""
    f = record_file(state, sid, name)
    rec = json.loads(f.read_text(encoding="utf-8"))
    for k, v in fields.items():
        rec.pop(k, None) if v is None else rec.__setitem__(k, v)
    f.write_text(json.dumps(rec), encoding="utf-8")


def aged_session(state, sid, home, hooks_dir=None):
    """Age every file in `home` by 60 s and give `sid` a record whose last check was 30 s ago,
    so only a change made afterwards can look newer than the check (the fixture's own fresh
    files would otherwise beat the seed and pass whether or not the feature works)."""
    t = time.time()
    for p in home.rglob("*"):
        if p.is_file():
            os.utime(p, (t - 60, t - 60))
    edit(state, sid, home, home / "model.R", hooks_dir)  # a non-doc edit: makes the record
    patch_record(state, sid, home.name, dirty=False, checked_at=t - 30)


def fold(state, home, *args, sid=None):
    env = {"CLAUDE_CODE_SESSION_ID": sid} if sid else None
    return run_hook("fold.py", None, state, input_text="", args=(args[0], str(home), *args[1:]),
                    extra_env=env)


def test_post_tool_use(base):
    top = base / "two homes"
    a, b = make_home(top, "proj-a"), make_home(top, "proj-b")
    state = base / "state_ptu"

    edit(state, "s1", top, a / "README.md")
    edit(state, "s1", top, b / "model.R")
    edit(state, "s1", top, a / "README.md")
    edit(state, "s1", top, top / "loose.md")
    run_hook("post_tool_use.py", {"session_id": "s1", "cwd": str(top), "tool_name": "NotebookEdit",
                                  "tool_input": {"notebook_path": str(b / "nb.ipynb")}}, state)
    recs = records(state, "s1")
    check("post_tool_use: credits each file to its own home, opened above both",
          set(recs) == {"proj-a", "proj-b"}, recs)
    check("post_tool_use: a record exists per home, notebook_path included",
          all(r.get("home") for r in recs.values()), recs)
    check("post_tool_use: a .md edit marks the home for checking, other files don't",
          recs["proj-a"].get("dirty") and not recs["proj-b"].get("dirty"), recs)




def test_stop(base):
    top = base / "stop homes"
    a, b = make_home(top, "proj-a", broken=True), make_home(top, "proj-b", broken=True)
    state = base / "state_stop"

    rc, out, err = stop(state, "nosuch", base)
    check("stop: outside every home, no edits - silent, nothing recorded",
          rc == 0 and not out and not err and not records(state, "nosuch"), (rc, out, err))

    rc, _, err = stop(state, "idle", a)
    rec = records(state, "idle").get("proj-a", {})
    check("stop: a session with no edits is recorded against its home",
          rc == 0 and rec.get("last_stop") and rec.get("transcript"), (rc, err, rec))

    edit(state, "r-only", top, b / "model.R")
    rc, _, err = stop(state, "r-only", top)
    check("stop: a code-only edit runs no checker, even in a broken home", rc == 0, err)
    check("stop: the first edit seeds checked_at", "checked_at" in records(state, "r-only")["proj-b"])

    edit(state, "md", top, a / "README.md")
    rc, _, err = stop(state, "md", top)
    check("stop: a .md edit in a broken home blocks", rc == 2 and "NOT_THERE" in err, (rc, err))
    check("stop: only the home whose .md changed is checked", "proj-b" not in err, err)
    rc, _, err = stop(state, "md", top, active=True)
    check("stop: stop_hook_active lets the session stop", rc == 0, err)
    rc, _, err = stop(state, "md", top)
    check("stop: a failing check stays marked, so the next Stop blocks again", rc == 2, err)

    edit(state, "md2", a, a / "README.md")
    stop(state, "md2", a, active=True)
    check("stop: a doc edited during the hook's own continuation stays marked",
          records(state, "md2")["proj-a"].get("dirty"), records(state, "md2"))
    edit(state, "md3", a, a / "README.md")
    rc, _, _ = stop(state, "md3", a)
    check("stop: a checker failure leaves dirty set",
          rc == 2 and records(state, "md3")["proj-a"].get("dirty"), records(state, "md3"))


def test_stop_broken_checker(base):
    """The hooks never run a project's own copy of the checker (D-022): a corrupt one in the
    project changes nothing."""
    repo = make_scratch_repo(base)
    (repo / "skills" / "repo-clean" / "scripts" / "check_docs.py").write_text(
        "raise RuntimeError('boom')\n", encoding="utf-8")
    state = base / "state_broken"
    edit(state, "bc1", repo, repo / "README.md")
    rc, out, err = stop(state, "bc1", repo)
    check("stop: a project's own broken checker is never run", rc == 0 and "boom" not in err,
          (rc, out, err))


def test_plugin_core(base):
    """The checker runs from the hook's own plugin folder, never the highest-numbered
    version in the plugin cache (a stray 9.9.9 folder once shadowed every release), and never
    a copy inside the project."""
    repo = make_scratch_repo(base)
    (repo / "skills" / "repo-clean" / "scripts" / "check_docs.py").unlink()
    fake_home = base / "fakehome"
    d = (fake_home / ".claude" / "plugins" / "cache" / "repo-clean" / "repo-clean" / "99.0.0"
         / "skills" / "repo-clean" / "scripts")
    d.mkdir(parents=True)
    (d / "check_docs.py").write_text("print('stub ran'); raise SystemExit(1)\n", encoding="utf-8")
    env = {"HOME": str(fake_home), "USERPROFILE": str(fake_home)}
    state = base / "state_plugincore"
    run_hook("post_tool_use.py", {"session_id": "pc1", "cwd": str(repo),
                                  "tool_input": {"file_path": str(repo / "README.md")}},
             state, extra_env=env)
    rc, out, err = run_hook("stop.py", {"session_id": "pc1", "cwd": str(repo)}, state,
                            extra_env=env)
    check("plugin core: a higher cached version does not change which checker runs",
          rc == 0 and "stub ran" not in err, (rc, err))


def stub_plugin(base, source):
    """A scratch copy of the plugin whose checker is replaced by `source`; its hooks dir."""
    plug = make_scratch_repo(base)
    (plug / "skills" / "repo-clean" / "scripts" / "check_docs.py").write_text(source, encoding="utf-8")
    return plug / "hooks"


def test_failing_checker(base):
    """A checker that crashes, is missing or times out is not a finding about the docs."""
    state = base / "state_failing"
    top = base / "failing homes"
    stub2 = stub_plugin(base, 'import sys\nif __name__ == "__main__":\n'
                              '    print("stub says boom"); sys.exit(2)\n')
    home = make_home(top, "h1")
    edit(state, "f1", home, home / "README.md", stub2)
    before = records(state, "f1")["h1"]
    rc, _, err = stop(state, "f1", home, hooks_dir=stub2)
    rec = records(state, "f1")["h1"]
    check("stop: a checker that exits 2 does not block", rc == 0, err)
    check("stop: ...and the home stays marked, checked_at unchanged",
          rec.get("dirty") and rec.get("checked_at") == before.get("checked_at"), rec)
    rc, out, _ = run_hook("session_start.py", {"session_id": "f2", "cwd": str(home),
                                               "source": "startup"}, state, hooks_dir=stub2)
    check("session_start: a checker that exits 2 is printed", "stub says boom" in out, out)

    # A timeout: patch subprocess.run inside a child interpreter, so the real code path
    # (run_checker -> 124 -> printed at session start) runs end to end.
    child = (
        "import subprocess, sys\n"
        "sys.stdout.reconfigure(encoding='utf-8')\n"
        f"sys.path.insert(0, {str(HOOKS_DIR)!r})\n"
        "def boom(*a, **k):\n    raise subprocess.TimeoutExpired('checker', 1)\n"
        "subprocess.run = boom\n"
        "import _lib, session_start\n"
        f"print(_lib.run_checker(__import__('pathlib').Path({str(home)!r}))[0])\n"
        "session_start.main()\n")
    out = subprocess.run([sys.executable, "-c", child], capture_output=True, text=True,
                         encoding="utf-8", env=dict(os.environ, REPO_CLEAN_HOME=str(state)),
                         input=json.dumps({"session_id": "f3", "cwd": str(home),
                                           "source": "startup"}))
    check("run_checker: a timeout is 124, not a finding", out.stdout.startswith("124\n"), out)
    check("session_start: a timeout is printed", "checker timed out" in out.stdout[4:], out.stdout + out.stderr)

    missing = stub_plugin(base, "")
    (missing.parent / "skills" / "repo-clean" / "scripts" / "check_docs.py").unlink()
    edit(state, "f4", home, home / "README.md", missing)
    rc, _, err = stop(state, "f4", home, hooks_dir=missing)
    check("stop: a missing checker is not recorded as clean and does not block",
          rc == 0 and records(state, "f4")["h1"].get("dirty"), (rc, err))
    rc, out, _ = run_hook("session_start.py", {"session_id": "f5", "cwd": str(home),
                                               "source": "startup"}, state, hooks_dir=missing)
    check("session_start: a missing checker is printed", "checker not found" in out, out)


def test_stop_any_change(base):
    """Stop checks docs changed by any means (a script, a command, another window), not only
    through the edit tool. Fixture files are aged and checked_at seeded 30 s back first."""
    state = base / "state_anychange"
    top = base / "anychange homes"

    h = make_home(top, "broken", broken=True)
    aged_session(state, "a1", h)
    rc, _, err = stop(state, "a1", h)
    check("stop: docs older than the last check, no edit - no check", rc == 0, err)
    (h / "README.md").write_text("See `docs/NOT_THERE.md` again.\n", encoding="utf-8")
    rc, _, err = stop(state, "a1", h)
    check("stop: a doc rewritten by command is checked", rc == 2 and "NOT_THERE" in err, (rc, err))
    rc, _, err = stop(state, "a1", h)
    check("stop: ...and still blocks on the next turn", rc == 2, err)
    (h / "README.md").write_text("fine\n", encoding="utf-8")
    seeded = records(state, "a1")["broken"]["checked_at"]
    rc, _, err = stop(state, "a1", h)
    check("stop: once fixed it passes and checked_at moves",
          rc == 0 and records(state, "a1")["broken"]["checked_at"] > seeded, (rc, err))

    h = make_home(top, "log", broken=False)
    aged_session(state, "a2", h)
    log = h / "docs" / "log" / "2026.md"
    log.write_text(log.read_text(encoding="utf-8") +
                   "\n## 2026-01-02 — more\n\nDecisions: none\nDocs: none\nState: two\nNext: x\n",
                   encoding="utf-8")
    rc, _, err = stop(state, "a2", h)
    check("stop: a second State: written into the log is caught", rc == 2 and "State:" in err,
          (rc, err))

    h = make_home(top, "routed", broken=False)
    (h / "guide").mkdir()
    (h / "guide" / "init.md").write_text("fine\n", encoding="utf-8")
    with (h / "CLAUDE.md").open("a", encoding="utf-8") as f:
        f.write("| guide | `guide/init.md` |\n")
    aged_session(state, "a3", h)
    (h / "guide" / "init.md").write_text("See `docs/GONE.md`.\n", encoding="utf-8")
    rc, _, err = stop(state, "a3", h)
    check("stop: a routed doc outside docs/ changed by command is caught",
          rc == 2 and "GONE" in err, (rc, err))

    h = make_home(top, "norecord", broken=True)
    aged_session(state, "a4", h)
    patch_record(state, "a4", "norecord", dirty=None, checked_at=None)
    rc, _, err = stop(state, "a4", h)
    check("stop: a record with neither checked_at nor dirty runs no check", rc == 0, err)

    parent = base / "anychange parent"
    h = make_home(parent, "proj", broken=True)
    for p in h.rglob("*"):
        if p.is_file():
            os.utime(p, (time.time() - 60,) * 2)
    edit(state, "a5", parent, h / "model.R")  # opened above the project; no doc edit yet
    time.sleep(0.05)
    (h / "README.md").write_text("See `docs/NOT_THERE.md` too.\n", encoding="utf-8")
    rc, _, err = stop(state, "a5", parent)
    check("stop: a project reached from a parent folder is checked for changes by command",
          rc == 2, (rc, err))

    stub = stub_plugin(base, 'raise ImportError("stub")\n')
    h = make_home(top, "noimport", broken=True)
    aged_session(state, "a6", h, stub)
    (h / "README.md").write_text("See `docs/NOT_THERE.md` x.\n", encoding="utf-8")
    rc, _, err = stop(state, "a6", h, hooks_dir=stub)
    check("stop: if the checker can't be imported the check still runs", rc == 2, (rc, err))
    rc, out, _ = run_hook("session_start.py", {"session_id": "a7", "cwd": str(h),
                                               "source": "startup"}, state, hooks_dir=stub)
    check("session_start: an unimportable checker is printed", "checker import failed" in out, out)


def test_records(base):
    state = base / "state_records"
    home = make_home(base, "records home")
    edit(state, "rc1", home, home / "README.md")
    record_file(state, "rc1", home.name).write_text("{not json", encoding="utf-8")
    rc, out, err = stop(state, "rc1", home)
    check("stop: a corrupt session record does not crash it", rc == 0, (out, err))
    rc, _, _ = run_hook("session_start.py", {"session_id": "rc1", "cwd": str(home),
                                             "source": "startup"}, state)
    files = list((state / "homes").rglob("*"))
    check("records: every record is valid JSON and no temp file is left behind",
          rc == 0 and not any(f.suffix == ".tmp" for f in files)
          and all(json.loads(f.read_text(encoding="utf-8")) is not None
                  for f in files if f.suffix == ".json"), files)


def test_session_start(base):
    repo = make_scratch_repo(base)
    state = base / "state_ss"
    expect = check_docs.current_fields(repo)

    rc, out, err = run_hook("session_start.py", {"session_id": "a1", "cwd": str(repo),
                                                 "source": "startup"}, state)
    check("session_start: prints State: and Next:",
          f"State: {expect['State']}" in out and f"Next: {expect['Next']}" in out, out)
    check("session_start: prints the plugin version",
          re.search(r"^repo-clean \d+\.\d+\.\d+$", out, re.M), out)
    check("session_start: nothing to fold in a fresh home", "not yet folded" not in out, out)

    stop(state, "earlier1", repo)
    stop(state, "earlier2", repo)
    ss = lambda sid, source: run_hook("session_start.py", {"session_id": sid, "cwd": str(repo),
                                                           "source": source}, state)[1]
    out = ss("new1", "startup")
    check("session_start: names un-folded sessions at startup",
          "2 earlier session(s) not yet folded" in out and "fold.py" in out, out)
    for source in ("resume", "clear", "compact"):
        check(f"session_start: no fold-in on {source}", "not yet folded" not in ss("x", source))

    rc, out, err = fold(state, repo, "list")
    check("fold list: lists both", rc == 0 and "earlier1" in out and "earlier2" in out, (out, err))
    stop(state, "late", repo)  # stops between list and done, so never listed
    rc, _, err = fold(state, repo, "done", sid="folder")
    check("fold done: refuses before the sessions have been read", rc == 1 and "earlier1" in err, err)
    rc, out, err = fold(state, repo, "read")
    check("fold read: transcripts that are gone are reported, and it exits 1",
          rc == 1 and out.count("transcript gone") == 2, (rc, out, err))
    rc, _, err = fold(state, repo, "done", sid="folder")
    check("fold done: exits 0 once everything listed has been read", rc == 0, err)
    check("session_start: DEF-34 - a session that stopped mid-fold-in is still waiting",
          "1 earlier session(s) not yet folded" in ss("new2", "startup"))
    stop(state, "folder", repo)
    check("session_start: DEF-33 - the folding session does not come back",
          "1 earlier session(s) not yet folded" in ss("new2b", "startup"))
    stop(state, "earlier1", repo)
    check("session_start: a folded session that kept working comes up again",
          "2 earlier session(s) not yet folded" in ss("new3", "startup"))

    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nSee `docs/GONE.md`.\n",
                      encoding="utf-8")
    out = ss("new4", "resume")
    check("session_start: prints a checker finding", "checker found problems" in out, out)
    edit(state, "new4", repo, repo / "model.R")
    rc, _, err = stop(state, "new4", repo)
    check("session_start: a problem that predates the session does not block its Stop",
          rc == 0, err)

    arrow = make_home(base, "arrow home")  # a → in State: must not crash on a cp1252 console
    rc, out, err = run_hook("session_start.py", {"session_id": "ar1", "cwd": str(arrow),
                                                 "source": "startup"}, base / "state_arrow")
    check("session_start: an arrow in the log exits 0 and prints the State line",
          rc == 0 and "ok → next" in out, (rc, out, err))

    tricky = make_home(base, "tricky home")
    (tricky / "docs" / "log" / "2026.md").write_text(
        "## 2026-01-01 — start\n\nDecisions: none\nDocs: none\n"
        "```\nState: fenced\n```\nState: a  Next: b\n", encoding="utf-8")
    rc, out, err = run_hook("session_start.py", {"session_id": "tr1", "cwd": str(tricky),
                                                 "source": "startup"}, base / "state_tricky")
    lines = out.splitlines()
    check("session_start: reads the log the checker's way (fence blanked, inline Next:)",
          lines[:2] == ["State: a", "Next: b"] and "fenced" not in out
          and re.fullmatch(r"repo-clean \d+\.\d+\.\d+", lines[2]), out)

    unset_repo = base / "réviser projet sans config"
    unset_repo.mkdir()
    ns = base / "state_ss_nosetup"
    _, out1, _ = run_hook("session_start.py", {"session_id": "b1", "cwd": str(unset_repo)}, ns)
    _, out2, _ = run_hook("session_start.py", {"session_id": "b2", "cwd": str(unset_repo)}, ns)
    check("session_start: setup offer fires once", "init" in out1, out1)
    check("session_start: setup offer silent second time", out2.strip() == "", out2)


def test_find_home(base):
    """D-018/D-023: the marker and the walk-up; the no-home glob; no pre-marker layout."""
    from _lib import find_home, find_homes_nearby

    repo = make_scratch_repo(base).resolve()
    check("find_home: marker at cwd is a home", find_home(repo) == repo, find_home(repo))
    check("find_home: walks up from a subfolder to the marker",
          find_home(repo / "docs" / "log") == repo)

    old = base / "pre-marker"
    (old / "docs" / "log").mkdir(parents=True)
    (old / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    check("find_home: CLAUDE.md + docs/log/ without the marker is not a home",
          find_home(old) is None, find_home(old))
    empty = base / "empty-no-home"
    empty.mkdir()
    check("find_home: no home above an unrelated empty folder", find_home(empty) is None)

    root = base / "shared-root"
    for n in ("proj-a", "proj-b", "proj-c", "proj-d"):
        make_home(root, n)
    pre = make_home(root / "group", "proj-old")
    (pre / ".repo-clean").unlink()
    check("find_homes_nearby: markers only, two levels down",
          {p.name for p in find_homes_nearby(root)} == {"proj-a", "proj-b", "proj-c", "proj-d"},
          find_homes_nearby(root))

    state = base / "state_shared_root"
    rc, out, _ = run_hook("session_start.py", {"session_id": "sr0", "cwd": str(root),
                                               "source": "startup"}, state)
    check("session_start: above homes with nothing to fold, names them", "proj-a" in out, out)
    for n in ("proj-a", "proj-b", "proj-c", "proj-d"):
        stop(state, f"w-{n}", root / n)
    rc, out, _ = run_hook("session_start.py", {"session_id": "sr1", "cwd": str(root),
                                               "source": "startup"}, state)
    check("session_start: above homes, one line with count, three names and N more",
          "4 home(s)" in out and "and 1 more" in out and out.count("\n") == 1, out)


def test_launcher(base):
    """run.sh finds a Python, or says there is none - on stdout for session_start (into
    Claude's context), on stderr for the other hooks - and exits 0 either way."""
    bash = shutil.which("bash")
    if not bash:
        print("skip: run.sh tests - no bash on PATH")
        return
    empty = base / "empty path"
    empty.mkdir()
    sh = str(HOOKS_DIR / "run.sh")

    def run(hook, env, text=""):
        return subprocess.run([bash, sh, hook, str(REPO_ROOT)], input=text, capture_output=True,
                              text=True, encoding="utf-8", env=env)

    bare = dict(os.environ, PATH=str(empty))
    out = run("session_start", bare)
    check("run.sh: no Python - session_start says so on stdout and exits 0",
          out.returncode == 0 and "no Python 3.8+ found" in out.stdout, out)
    out = run("stop", bare)
    check("run.sh: no Python - stop says so on stderr and exits 0",
          out.returncode == 0 and "no Python 3.8+ found" in out.stderr and not out.stdout, out)
    out = run("stop", dict(os.environ, REPO_CLEAN_HOME=str(base / "state_launcher")), "{}")
    check("run.sh: with Python, it runs the hook", out.returncode == 0 and not out.stderr, out)


def tline(who, content, ts=None, **extra):
    d = {"type": who, "message": {"role": who, "content": content}}
    if ts:
        d["timestamp"] = ts
    d.update(extra)
    return json.dumps(d)


OLD, FUTURE = "2020-01-01T00:00:00.000Z", "2099-01-01T00:00:00.000Z"


def test_fold_read(base):
    """The transcript reader keeps words, edited paths and the user's answers, drops tool
    output, and prints only what is newer than the last fold-in."""
    home = make_home(base, "fold home")
    t = base / "t.jsonl"
    lines = [
        tline("user", "fix the chart <system-reminder>noise</system-reminder>", OLD),
        tline("assistant", [
            {"type": "thinking", "thinking": "secret"},
            {"type": "text", "text": "Fixed the axis."},
            {"type": "tool_use", "id": "b1", "name": "Edit", "input": {"file_path": "C:/p/chart.R"}},
            {"type": "tool_use", "id": "b2", "name": "Bash",
             "input": {"command": "select * from patients"}}], OLD),
        tline("user", [{"type": "tool_result", "tool_use_id": "b2", "content": "MRN 12345"}], OLD),
        tline("assistant", [{"type": "text", "text": "subagent chatter"}], OLD, isSidechain=True),
        tline("assistant", [{"type": "tool_use", "id": "q1", "name": "AskUserQuestion",
                             "input": {"questions": []}}], OLD),
        tline("user", [{"type": "tool_result", "tool_use_id": "q1",
                        "content": 'User has answered: "Which?"="blue"'}], OLD),
        "not json",
    ]
    t.write_text("\n".join(lines) + "\n", encoding="utf-8")
    state = base / "state_fold"
    stop(state, "f1", home, transcript=t)
    rc, out, err = fold(state, home, "list")
    check("fold list: shows the waiting session", rc == 0 and "f1" in out, (out, err))
    rc, out, err = fold(state, home, "read")
    check("fold read: user and Claude words, edited paths",
          rc == 0 and "[user] fix the chart" in out and "[claude] Fixed the axis." in out
          and "[edited] C:/p/chart.R" in out, (out, err))
    check("fold read: the user's answer to a question is kept",
          '[user answer] User has answered: "Which?"="blue"' in out, out)
    check("fold read: no tool output, commands, thinking, side chains or reminders",
          not any(s in out for s in ("MRN", "patients", "secret", "subagent", "noise")), out)
    check("fold read: a short session is one page", "-- more" not in out, out)
    rc, _, err = fold(state, home, "done")
    check("fold done: after a full read", rc == 0, err)

    stop(state, "f1", home, transcript=t)
    fold(state, home, "list")
    rc, out, _ = fold(state, home, "read")
    check("fold read: a stop with nothing new says so", rc == 0 and "nothing new" in out, out)
    fold(state, home, "done")

    with t.open("a", encoding="utf-8") as f:
        f.write(tline("user", "beta has no timestamp") + "\n")
        f.write(tline("user", "gamma is new", FUTURE) + "\n")
    stop(state, "f1", home, transcript=t)
    fold(state, home, "list")
    rc, out, err = fold(state, home, "read")
    check("fold read: after a fold-in, only the new entries - and one with no timestamp",
          "gamma is new" in out and "beta has no timestamp" in out and "fix the chart" not in out,
          (out, err))
    fold(state, home, "done")

    state = base / "state_fold_long"
    t2 = base / "long.jsonl"
    t2.write_text("\n".join(tline("user", f"entry {i} " + "x" * 1500, OLD) for i in range(30)) + "\n",
                  encoding="utf-8")
    stop(state, "f2", home, transcript=t2)
    fold(state, home, "list")
    rc, out, _ = fold(state, home, "read")
    check("fold read: a long session pages and says how to continue",
          rc == 0 and "-- more:" in out and "entry 0 " in out and "entry 29 " not in out
          and "--from" in out, out[-300:])
    rc, _, err = fold(state, home, "done")
    check("fold done: refuses after a partial read, naming the session", rc == 1 and "f2" in err, err)
    for _ in range(10):
        m = re.search(r"--from (\d+)", out)
        if not m:
            break
        rc, out, _ = fold(state, home, "read", "--from", m.group(1))
    check("fold read: --from reaches the last entry", "entry 29 " in out and "-- more" not in out, out[-300:])
    rc, _, err = fold(state, home, "done")
    check("fold done: succeeds once read to the end", rc == 0, err)

    state = base / "state_fold_lost"
    bad = base / "bad.jsonl"
    bad.write_text('{"type": "summary"}\n', encoding="utf-8")
    stop(state, "good", home, transcript=t)
    stop(state, "bad", home, transcript=bad)
    stop(state, "gone", home)
    fold(state, home, "list")
    rc, out, err = fold(state, home, "read")
    check("fold read: one session read, one unreadable, one gone - it carries on",
          rc == 0 and "[user] fix the chart" in out and "[session bad: unreadable" in out
          and "[session gone: transcript gone" in out, (rc, out, err))
    state = base / "state_fold_alllost"
    stop(state, "bad", home, transcript=bad)
    stop(state, "gone", home)
    fold(state, home, "list")
    rc, out, _ = fold(state, home, "read")
    check("fold read: every session unreadable or gone - exits 1", rc == 1, (rc, out))

    state = base / "state_fold_check"
    stop(state, "c1", home, transcript=t)
    rc, out, _ = fold(state, home, "list", "--check")
    check("fold list --check: writes nothing", rc == 0 and "listed_stop" not in
          json.dumps(records(state, "c1")), records(state, "c1"))
    rc, out, _ = fold(state, home, "read")
    check("fold read: still works after list --check", rc == 0 and "fix the chart" in out, out)


def test_bad_input(base):
    state = base / "state_bad"
    for hook in ("post_tool_use.py", "stop.py", "session_start.py"):
        for text in ("", "not json{{{", json.dumps({"foo": "bar"}), "[1, 2]"):
            rc, out, err = run_hook(hook, None, state, input_text=text)
            check(f"{hook}: bad stdin {text[:8]!r} exits 0", rc == 0, (out, err))


def test_check_docs_no_home(base):
    """With nothing to check the checker exits 2 - it does not pass."""
    core = REPO_ROOT / "skills" / "repo-clean" / "scripts" / "check_docs.py"
    tmp = base / "no-home-folder"
    tmp.mkdir()

    def run(*args, cwd=None):
        return subprocess.run([sys.executable, str(core), *args], capture_output=True, text=True,
                              encoding="utf-8", cwd=cwd)

    out = run("--root", str(tmp))
    check("check_docs.py --root: not a home - says so and exits 2",
          out.returncode == 2 and "no repo-clean home" in out.stdout, out.stdout + out.stderr)
    out = run(cwd=tmp)
    check("check_docs.py: no --root and no marker above - exits 2",
          out.returncode == 2 and "at or above" in out.stdout, out.stdout + out.stderr)
    home = make_home(base, "walk home")
    out = run(cwd=home / "docs")
    check("check_docs.py: no --root walks up to the marker", out.returncode == 0, out.stdout)
    check("check_docs.py: removed flags are rejected",
          all(run(f).returncode == 2 for f in ("--selfcheck", "--version", "--init-config")))


def test_checker_rules(base):
    """Every rule fires on what it should and stays quiet on what it shouldn't."""
    tmp = base / "rules fixture"
    (tmp / "docs" / "log").mkdir(parents=True)
    (tmp / "docs" / "archive").mkdir(parents=True)
    (tmp / "scripts" / "tools").mkdir(parents=True)
    # DEF-02 quiet case: this stand-in is what a backticked command with a flag names.
    (tmp / "scripts" / "tools" / "check_docs.py").write_text("# stand-in\n", encoding="utf-8")
    (tmp / "docs" / "archive" / "BANNER.md").write_text("archived\n", encoding="utf-8")

    (tmp / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n"
        "| ID | Question | Revisit |\n"
        "|---|---|---|\n"
        "| D-999 | ghost row, not an open entry below | never |\n\n"
        "## Fields\n\n"
        "## D-001 \u2014 a\n"
        "Status: active   Verdict: adopted extra words   Superseded-by: D-002\n\n"
        "## D-002 \u2014 b\n"
        "Status: superseded   Verdict: adopted\n\n"
        "## D-003 \u2014 c\n"
        "Status: open   Verdict: unresolved\n\n"
        # DEF-09 fire case: a title containing "Revisit" must not satisfy the real
        # Revisit: field requirement - the body has none, so this must still fire.
        "## D-778 \u2014 Revisit later\n"
        "Status: open   Verdict: unresolved\n\n"
        # DEF-08 quiet case: prose mentions Superseded-by: with a single space, and a
        # dangling-looking id, but must not be parsed as a real field.
        "## D-777 \u2014 prose mentions a field name\n"
        "Status: active   Verdict: adopted\n"
        "Why: We considered Superseded-by: D-889 but rejected the idea.\n\n"
        # DEF-07 fire case: one decision superseding two, both directions must match.
        "## D-010 \u2014 consolidates two\n"
        "Status: active   Verdict: adopted   Supersedes: D-011, D-012\n\n"
        "## D-011 \u2014 folded in, symmetric\n"
        "Status: superseded   Verdict: adopted   Superseded-by: D-010\n\n"
        "## D-012 \u2014 folded in, NOT symmetric (missing Superseded-by)\n"
        "Status: superseded   Verdict: adopted\n\n"
        # D-016(c): the register is not exempt from the banned header.
        "## Next Steps in the register\n",
        encoding="utf-8",
    )
    (tmp / "CLAUDE.md").write_text(
        "| Doc | Path |\n"
        "|---|---|\n"
        "| routed doc | `./docs/ROUTED.md` |\n"
        "| checker | `scripts/tools/check_docs.py --root .` |\n\n"
        "See `docs/DOES_NOT_EXIST.md` and `C:\\Users\\x\\.claude\\plans\\p.md`.\n"
        "and a unix one `/home/me/notes.md`, and a Git Bash one `/c/Users/me/notes.md`.\n"
        "## Next Steps later\n"
        # D-017: TODO/Future Work headers are no longer banned, only Next Steps.
        "## TODO no longer banned\n"
        "`docs/SUPPRESSED_MISSING.md` should not fire. <!-- check-docs: ignore paths-exist -->\n"
        # DEF-22 fire cases: wrong case, and a non-directory with a trailing slash.
        "Wrong case: `docs/Archive/BANNER.md`. Not a dir: `docs/archive/BANNER.md/`.\n"
        # DEF-22 quiet case: correct case, and a real directory with a trailing slash.
        "Right case: `docs/archive/BANNER.md`. Real dir: `docs/archive/`.\n"
        # DEF-15 fire case: a stray backtick mention outside the table must not count
        # as routing docs/ORPHAN.md.
        "By the way, `docs/ORPHAN.md` is mentioned here in prose, not the table.\n",
        encoding="utf-8",
    )
    (tmp / "README.md").write_text("fine\n", encoding="utf-8")
    (tmp / "docs" / "ROUTED.md").write_text("routed via the table with a leading ./\n", encoding="utf-8")
    (tmp / "docs" / "MOJIBAKE.md").write_bytes(b"# t\n\xff\xfe not utf-8\n")
    (tmp / "docs" / "ORPHAN.md").write_text("unrouted doc\n", encoding="utf-8")
    (tmp / "docs" / "FENCED.md").write_text(
        "# fenced\n"
        "Real content.\n"
        "```markdown\n"
        "## D-999 \u2014 a fake decision heading inside a fence\n"
        "Status: nonsense\n"
        "## Next Steps inside a fence\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "log" / "2099-01.md").write_text(
        "## 2099-01-01 \u2014 wrapped fields\n"
        "Decisions: D-999\n"
        # DEF-05 fire case: Docs: wraps across lines; the second line's missing file
        # must still be caught.
        "Docs: nope.md\n"
        "more-missing.md\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "log" / "2098-08.md").write_text(
        "## 2098-01-01 \u2014 first entry\n"
        "Decisions: none\n"
        "Docs: none\n\n"
        "body text with an outside path C:\\Users\\x\\plan.md and a banned header below\n\n"
        "## Next Steps later\n\n"
        "### 2098-02-02 old-style heading after the first '##' heading\n\n"
        "## 2098-01-01 \u2014 duplicate date and no N\n"
        "Docs: none\n"
        "State: stale\n\n"
        "## 2098-01-03 bad grammar no dash\n"
        "Decisions: none\n\n"
        "## 2098-01-04 (1) \u2014 last entry missing state\n"
        "Decisions: none\n"
        "Docs: none\n",
        encoding="utf-8",
    )

    found = []
    check_docs.run_generic_rules(check_docs.Ctx(tmp, dict(check_docs.CONFIG)), found)

    def has(*substrings):
        return any(all(s in e for s in substrings) for e in found)

    def none_has(*substrings):
        return not any(all(s in e for s in substrings) for e in found)

    for label, ok in {
        "bad/missing Verdict": has("bad/missing Verdict"),
        "Docs: field finding": has("Docs:"),
        "outside-repo path": has("absolute/outside-repo path in a living doc"),
        "missing path fires, suppressed one does not": has("does not exist") and none_has("SUPPRESSED_MISSING"),
        "banned header": has("banned section"),
        "TODO is no longer banned (D-017)": none_has("banned section", "TODO"),
        "Next Steps in DECISIONS.md is banned (D-016(c))": has("DECISIONS.md", "banned section header"),
        "missing Decisions:": has("missing a Decisions:"),
        "missing Docs:": has("missing a Docs:"),
        "last entry missing State:": has("missing a non-empty State:"),
        "State: on a non-last entry": has("carries a State: line but is not"),
        "diary grammar": has("diary heading grammar violated"),
        "duplicate diary heading": has("duplicate diary heading"),
        "### heading after ##": has("'###' dated heading appears after"),
        "open-questions table sync": has("missing from the Open questions table") or has("is not Status: open"),
        "open entry with no Revisit:": has("no Revisit:"),
        "unrouted doc": has("not referenced in"),
        "Decisions: references an unknown id": has("Decisions: references unknown"),
        "abs path in CLAUDE.md (unix, Git Bash, drive)": has("CLAUDE.md:", "absolute/outside-repo path"),
        "a one-line multi-field entry parses (D-003)": none_has("D-003", "bad/missing"),
        "DEF-02: a backticked command with a flag is not a missing path": none_has("check_docs.py"),
        "DEF-05: a wrapped Docs: value is read to its last line": has("more-missing.md"),
        "DEF-07: symmetric supersession is quiet": not any(
            "D-010" in e and "D-011" in e and "not symmetric" in e for e in found),
        "DEF-07: asymmetric supersession fires": any(
            "D-010" in e and "D-012" in e and "not symmetric" in e for e in found),
        "DEF-08: prose 'Superseded-by:' is not a field": none_has("D-777") and none_has("D-889"),
        "DEF-09: 'Revisit' in a title does not satisfy the field":
            any("D-778" in e and "no Revisit:" in e for e in found),
        "DEF-10: fenced content is not read": none_has("D-999", "bad/missing"),
        "DEF-15: table routing, ./ normalized, a prose mention does not count":
            none_has("docs/ROUTED.md", "not referenced")
            and any("docs/ORPHAN.md" in e and "not referenced" in e for e in found),
        "DEF-18: (N) numbering": has("heading numbering"),
        "DEF-22: wrong case": has("docs/Archive/BANNER.md"),
        "DEF-22: a file with a trailing slash": has("docs/archive/BANNER.md/"),
        "DEF-22: right case and a real directory are quiet": not any(
            e.rstrip().endswith("docs/archive/BANNER.md") and "does not exist" in e for e in found)
            and not any(e.split()[-1] == "docs/archive/" for e in found),
    }.items():
        check(f"rules: {label}", ok, found if not ok else "")

    # DEF-27: State:/Next: only on the log's last entry, across period files.
    h = base / "rollover fixture"
    (h / "docs" / "log").mkdir(parents=True)
    (h / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n## Fields\n\n## D-001 \u2014 a\nStatus: active   Verdict: adopted\n",
        encoding="utf-8")
    (h / "CLAUDE.md").write_text("nothing to route\n", encoding="utf-8")
    (h / "README.md").write_text("fine\n", encoding="utf-8")
    (h / "docs" / "log" / "2097-01.md").write_text(
        "## 2097-01-01 \u2014 first period, no state\nDecisions: none\nDocs: none\n", encoding="utf-8")
    (h / "docs" / "log" / "2097-02.md").write_text(
        "## 2097-02-01 \u2014 second period, first entry\nDecisions: none\nDocs: none\n\n"
        "## 2097-02-02 \u2014 second period, last entry\nDecisions: none\nDocs: none\nState: current\n",
        encoding="utf-8")
    ctx = check_docs.Ctx(h, dict(check_docs.CONFIG))
    f1 = []
    check_docs.run_generic_rules(ctx, f1)
    check("rules: DEF-27 State: on the last entry only is fine",
          not any("State:" in e for e in f1), f1)
    check("rules: D-016(c) the last entry must carry Next: too",
          any("missing a non-empty Next:" in e for e in f1), f1)
    with (h / "docs" / "log" / "2097-02.md").open("a", encoding="utf-8") as f:
        f.write("Next: keep going\n")
    with (h / "docs" / "log" / "2097-01.md").open("a", encoding="utf-8") as f:
        f.write("State: old\nNext: old\n")
    f2 = []
    check_docs.run_generic_rules(ctx, f2)
    check("rules: DEF-27 a State:/Next: on an earlier period file is one finding each",
          not any("missing a non-empty" in e for e in f2)
          and all(len([e for e in f2 if f"carries a {k}:" in e and "2097-01.md" in e]) == 1
                  for k in ("State", "Next")), f2)
    cf = check_docs.current_fields(h)
    check("rules: current_fields is the last entry's fields", cf.get("State") == "current"
          and cf.get("Next") == "keep going", cf)

    # D-020: a .md the routing table names outside docs/ is read like any living doc.
    (h / "sub").mkdir()
    (h / "sub" / "README.md").write_text("See `docs/NOT_THERE.md`.\n", encoding="utf-8")
    (h / "CLAUDE.md").write_text("| Q | A |\n|---|---|\n| sub | `sub/README.md` |\n", encoding="utf-8")
    f3 = []
    check_docs.run_generic_rules(ctx, f3)
    check("rules: D-020 a routed doc outside docs/ is checked",
          any("README.md" in e and "NOT_THERE.md" in e for e in f3), f3)

    # the CLI refuses what it cannot check
    f = base / "a file"
    f.write_text("x\n", encoding="utf-8")
    check("rules: DEF-21 --root at a file exits 2", check_docs.main(["--root", str(f)]) == 2)
    try:
        check_docs.main(["--bogus"])
        check("rules: DEF-19 an unknown flag exits", False, "no SystemExit")
    except SystemExit as e:
        check("rules: DEF-19 an unknown flag exits 2", e.code == 2, e.code)


def main():
    with tempfile.TemporaryDirectory(prefix="repo_clean_selftest_") as tmp:
        base = Path(tmp)
        test_post_tool_use(base)
        test_stop(base)
        test_stop_broken_checker(base)
        test_failing_checker(base)
        test_stop_any_change(base)
        test_records(base)
        test_session_start(base)
        test_find_home(base)
        test_plugin_core(base)
        test_launcher(base)
        test_fold_read(base)
        test_bad_input(base)
        test_check_docs_no_home(base)
        test_checker_rules(base)

    if _FAILURES:
        print(f"\n{len(_FAILURES)} failure(s):", file=sys.stderr)
        for f in _FAILURES:
            print(f" - {f}", file=sys.stderr)
        return 1
    print("\nselftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
