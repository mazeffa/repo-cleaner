#!/usr/bin/env python3
"""Self-test for hooks/. Stdlib only. `python hooks/selftest.py` exits 0 or asserts.
Run by hand; nothing runs it automatically (D-021).

Drives each hook via subprocess against a scratch copy of this repo (a known-good doc
tree), under a temp dir whose path has both a non-ASCII char and a space, so path
handling bugs surface here instead of in a real session. Registry/offer state is
isolated per test via REPO_CLEAN_HOME so this never touches a real user's data.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
FIXTURES_DIR = HOOKS_DIR / "fixtures"
sys.path.insert(0, str(HOOKS_DIR))

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
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".repo-clean"),
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


def run_hook(name, data, home, input_text=None, extra_env=None, args=()):
    env = dict(os.environ)
    env["REPO_CLEAN_HOME"] = str(home)
    env.pop("CLAUDE_CODE_SESSION_ID", None)  # this session's own id must not leak in
    if extra_env:
        env.update(extra_env)
    stdin = input_text if input_text is not None else json.dumps(payload(name, data or {}))
    out = subprocess.run(
        [sys.executable, str(HOOKS_DIR / name), *args],
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


def edit(state, sid, cwd, path):
    run_hook("post_tool_use.py", {"session_id": sid, "cwd": str(cwd),
                                  "tool_input": {"file_path": str(path)}}, state)


def stop(state, sid, cwd, active=False):
    return run_hook("stop.py", {"session_id": sid, "cwd": str(cwd),
                                "stop_hook_active": active}, state)


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
    """run_checker() shells out to the checker rather than importing it, so a corrupt
    working-tree copy (D-015) blocks with a clean message instead of crashing Stop."""
    repo = make_scratch_repo(base)
    (repo / "skills" / "repo-clean" / "scripts" / "check_docs.py").write_text(
        "raise RuntimeError('boom')\n", encoding="utf-8")
    state = base / "state_broken"
    edit(state, "bc1", repo, repo / "README.md")
    rc, out, err = stop(state, "bc1", repo)
    check("stop: broken checker blocks without a traceback",
          rc == 2 and "Traceback" not in err, (rc, out, err))


def test_session_start(base):
    repo = make_scratch_repo(base)
    state = base / "state_ss"
    from _lib import last_field, last_state_line, NEXT_RE

    rc, out, err = run_hook("session_start.py", {"session_id": "a1", "cwd": str(repo),
                                                 "source": "startup"}, state)
    # The scratch repo is a legacy home (CLAUDE.md + docs/log/, no .repo-clean marker
    # yet), so the first session here also gets the one-shot migrate hint (D-018).
    check("session_start: legacy home gets the migrate hint", "init --migrate" in out, out)
    check("session_start: prints State: and Next:",
          last_state_line(repo) in out and last_field(repo, NEXT_RE) in out, out)
    check("session_start: nothing to fold in a fresh home", "not yet folded" not in out, out)
    rc, out2, _ = run_hook("session_start.py", {"session_id": "a2", "cwd": str(repo),
                                                "source": "startup"}, state)
    check("session_start: migrate hint silent second time", "init --migrate" not in out2, out2)

    stop(state, "earlier1", repo)
    stop(state, "earlier2", repo)
    ss = lambda sid, source: run_hook("session_start.py", {"session_id": sid, "cwd": str(repo),
                                                           "source": source}, state)[1]
    out = ss("new1", "startup")
    check("session_start: names un-folded sessions at startup",
          "2 earlier session(s) not yet folded" in out and "fold.py" in out, out)
    for source in ("resume", "clear", "compact"):
        check(f"session_start: no fold-in on {source}", "not yet folded" not in ss("x", source))

    rc, out, err = run_hook("fold.py", None, state, input_text="", args=("list", str(repo)))
    check("fold list: lists both", rc == 0 and "earlier1" in out and "earlier2" in out, (out, err))
    ids = out.rsplit('" ', 1)[1].split()  # the `done` line's id@ts pairs
    stop(state, "late", repo)  # stops between list and done, so never listed
    rc, _, err = run_hook("fold.py", None, state, input_text="", args=("done", str(repo), *ids),
                          extra_env={"CLAUDE_CODE_SESSION_ID": "folder"})
    check("fold done: exits 0", rc == 0, err)
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

    arrow = make_home(base, "arrow home")  # a → in State: must not crash on a cp1252 console
    rc, out, err = run_hook("session_start.py", {"session_id": "ar1", "cwd": str(arrow),
                                                 "source": "startup"}, base / "state_arrow")
    check("session_start: an arrow in the log exits 0 and prints the State line",
          rc == 0 and "ok → next" in out, (rc, out, err))

    unset_repo = base / "réviser projet sans config"
    unset_repo.mkdir()
    ns = base / "state_ss_nosetup"
    _, out1, _ = run_hook("session_start.py", {"session_id": "b1", "cwd": str(unset_repo)}, ns)
    _, out2, _ = run_hook("session_start.py", {"session_id": "b2", "cwd": str(unset_repo)}, ns)
    check("session_start: setup offer fires once", "init" in out1, out1)
    check("session_start: setup offer silent second time", out2.strip() == "", out2)


def test_find_home(base):
    """D-018: the marker, the walk-up, the no-home glob, and the legacy fallback."""
    from _lib import find_home, find_homes_nearby

    repo = make_scratch_repo(base).resolve()
    (repo / ".repo-clean").write_text("", encoding="utf-8")
    home, legacy = find_home(repo)
    check("find_home: marker at cwd is a home", home == repo and not legacy, (home, legacy))
    home, legacy = find_home(repo / "docs" / "log")
    check("find_home: walks up from a subfolder to the marker", home == repo, home)

    legacy_repo = make_scratch_repo(base).resolve()  # no marker: CLAUDE.md + docs/log/ only
    home, legacy = find_home(legacy_repo)
    check("find_home: legacy home (no marker) still resolves", home == legacy_repo and legacy,
          (home, legacy))

    empty = base / "empty-no-home"
    empty.mkdir()
    home, legacy = find_home(empty)
    check("find_home: no home above an unrelated empty folder",
          home is None or home not in (repo, legacy_repo), home)

    root = base / "shared-root"
    for n in ("proj-a", "proj-b", "proj-c", "proj-d"):
        make_home(root, n)
    old = make_home(root / "group", "proj-old")
    (old / ".repo-clean").unlink()  # pre-marker home, two levels down
    nearby = find_homes_nearby(root)
    check("find_homes_nearby: markers and pre-marker homes, two levels down",
          {p.name for p in nearby} == {"proj-a", "proj-b", "proj-c", "proj-d", "proj-old"}, nearby)

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


def test_plugin_core(base):
    """The checker runs from the hook's own plugin folder, never the highest-numbered
    version in the plugin cache (a stray 9.9.9 folder once shadowed every release)."""
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


def test_fold_read(base):
    """P3: the transcript reader keeps words and edited paths, drops tool output."""
    t = base / "t.jsonl"
    lines = [
        {"type": "user", "message": {"content": "fix the chart <system-reminder>noise</system-reminder>"}},
        {"type": "assistant", "message": {"content": [
            {"type": "thinking", "thinking": "secret"},
            {"type": "text", "text": "Fixed the axis."},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "C:/p/chart.R"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "select * from patients"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "content": "MRN 12345"}]}},
        {"type": "assistant", "isSidechain": True, "message": {"content": [
            {"type": "text", "text": "subagent chatter"}]}},
    ]
    t.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n", encoding="utf-8")
    rc, out, err = run_hook("fold.py", None, base / "state_fold", input_text="",
                            args=("read", str(t)))
    check("fold read: user and Claude words, edited paths",
          rc == 0 and "[user] fix the chart" in out and "[claude] Fixed the axis." in out
          and "[edited] C:/p/chart.R" in out, (out, err))
    check("fold read: no tool output, commands, thinking, side chains or reminders",
          not any(s in out for s in ("MRN", "patients", "secret", "subagent", "noise")), out)

    (base / "empty.jsonl").write_text('{"type": "summary"}\n', encoding="utf-8")
    rc, _, err = run_hook("fold.py", None, base / "state_fold", input_text="",
                          args=("read", str(base / "empty.jsonl")))
    check("fold read: recognizes nothing - exits 1 and says so",
          rc == 1 and "recognized nothing" in err, (rc, err))
    rc, _, err = run_hook("fold.py", None, base / "state_fold", input_text="",
                          args=("read", str(base / "gone.jsonl")))
    check("fold read: expired transcript - exits 1, says detail was lost",
          rc == 1 and "detail was lost" in err, (rc, err))


def test_bad_input(base):
    state = base / "state_bad"
    for hook in ("post_tool_use.py", "stop.py", "session_start.py"):
        for text in ("", "not json{{{", json.dumps({"foo": "bar"}), "[1, 2]"):
            rc, out, err = run_hook(hook, None, state, input_text=text)
            check(f"{hook}: bad stdin {text[:8]!r} exits 0", rc == 0, (out, err))


def test_check_docs_no_home(base):
    """3a: `check_docs.py --root` on a folder that is neither markered nor the legacy
    CLAUDE.md + docs/log/ layout says so and exits 0, instead of checking it as if it were
    a repo-clean home."""
    tmp = base / "no-home-folder"
    tmp.mkdir()
    (tmp / "somefile.txt").write_text("x\n", encoding="utf-8")
    core = REPO_ROOT / "skills" / "repo-clean" / "scripts" / "check_docs.py"
    out = subprocess.run([sys.executable, str(core), "--root", str(tmp)],
                          capture_output=True, text=True, encoding="utf-8")
    check("check_docs.py --root: no home says so and exits 0",
          out.returncode == 0 and "no repo-clean home" in out.stdout, out.stdout + out.stderr)


def main():
    with tempfile.TemporaryDirectory(prefix="repo_clean_selftest_") as tmp:
        base = Path(tmp)
        test_post_tool_use(base)
        test_stop(base)
        test_stop_broken_checker(base)
        test_session_start(base)
        test_find_home(base)
        test_plugin_core(base)
        test_fold_read(base)
        test_bad_input(base)
        test_check_docs_no_home(base)

    if _FAILURES:
        print(f"\n{len(_FAILURES)} failure(s):", file=sys.stderr)
        for f in _FAILURES:
            print(f" - {f}", file=sys.stderr)
        return 1
    print("\nselftest ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
