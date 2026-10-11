#!/usr/bin/env python3
"""Self-test for hooks/. Stdlib only. `python hooks/selftest.py` exits 0 or asserts.
Run by hand; nothing runs it automatically.

Drives each hook via subprocess against a scratch copy of this repo (a known-good doc
tree), under a temp dir whose path has both a non-ASCII char and a space, so path
handling bugs surface here instead of in a real session. Offer state is
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
        "## Open questions\n\n## Fields\n\n## D-001 — a\nStatus: active\n",
        encoding="utf-8")
    (h / "docs" / "log" / "2026.md").write_text(
        "## 2026-01-01 — start\n\nDecisions: D-001\nDocs: CLAUDE.md\nLeft off: ok → next\n",
        encoding="utf-8")
    return h


def payload(fields):
    """Test fields overlaid on the real payload captured from a live Claude Code session
    (hooks/fixtures/SessionStart.json), so every assertion runs against the real key set."""
    f = FIXTURES_DIR / "SessionStart.json"
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    data.update(fields)
    return data


def run_hook(name, data, home, input_text=None, extra_env=None, args=(), hooks_dir=None):
    env = dict(os.environ)
    env["REPO_CLEAN_HOME"] = str(home)
    if extra_env:
        env.update(extra_env)
    stdin = input_text if input_text is not None else json.dumps(payload(data or {}))
    out = subprocess.run(
        [sys.executable, str((hooks_dir or HOOKS_DIR) / name), *args],
        input=stdin, capture_output=True, text=True, encoding="utf-8", env=env,
    )
    return out.returncode, out.stdout, out.stderr


def test_project_checker_never_run(base):
    """The hook never runs a project's own copy of the checker (D-022): a corrupt one in the
    project changes nothing."""
    repo = make_scratch_repo(base)
    (repo / "skills" / "repo-clean" / "scripts" / "check_docs.py").write_text(
        "raise RuntimeError('boom')\n", encoding="utf-8")
    state = base / "state_broken"
    rc, out, err = run_hook("session_start.py", {"session_id": "bc1", "cwd": str(repo),
                                                 "source": "startup"}, state)
    check("session_start: a project's own broken checker is never run",
          rc == 0 and "boom" not in out + err, (rc, out, err))


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
    rc, out, err = run_hook("session_start.py", {"session_id": "pc1", "cwd": str(repo),
                                                 "source": "startup"}, state, extra_env=env)
    check("plugin core: a higher cached version does not change which checker runs",
          rc == 0 and "stub ran" not in out, (rc, out, err))


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
    rc, out, _ = run_hook("session_start.py", {"session_id": "f2", "cwd": str(home),
                                               "source": "startup"}, state, hooks_dir=stub2)
    check("session_start: a checker that exits 2 is printed as the checker failing",
          "stub says boom" in out and "checker itself failed" in out, out)

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
    rc, out, _ = run_hook("session_start.py", {"session_id": "f5", "cwd": str(home),
                                               "source": "startup"}, state, hooks_dir=missing)
    check("session_start: a missing checker is printed", "checker not found" in out, out)


def test_session_start(base):
    repo = make_scratch_repo(base)
    state = base / "state_ss"
    body = "\n".join(check_docs.log_entries(check_docs.Ctx(repo))[-1][2]).strip()

    rc, out, err = run_hook("session_start.py", {"session_id": "a1", "cwd": str(repo),
                                                 "source": "startup"}, state)
    check("session_start: prints the last entry's body", body and body in out, out)
    check("session_start: prints the plugin version",
          re.search(r"^repo-clean \d+\.\d+\.\d+$", out, re.M), out)

    ss = lambda sid, source: run_hook("session_start.py", {"session_id": sid, "cwd": str(repo),
                                                           "source": source}, state)[1]
    readme = repo / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nSee `docs/GONE.md`.\n",
                      encoding="utf-8")
    out = ss("new4", "resume")
    check("session_start: prints a checker finding", "checker found problems" in out, out)

    arrow = make_home(base, "arrow home")  # a → in the log must not crash on a cp1252 console
    rc, out, err = run_hook("session_start.py", {"session_id": "ar1", "cwd": str(arrow),
                                                 "source": "startup"}, base / "state_arrow")
    check("session_start: an arrow in the log exits 0 and prints the body line",
          rc == 0 and "ok → next" in out, (rc, out, err))

    tricky = make_home(base, "tricky home")
    (tricky / "docs" / "log" / "2026.md").write_text(
        "## 2026-01-01 — start\n\nDecisions: none\nDocs: none\n"
        "```\nfenced\n```\nleft off here\n", encoding="utf-8")
    rc, out, err = run_hook("session_start.py", {"session_id": "tr1", "cwd": str(tricky),
                                                 "source": "startup"}, base / "state_tricky")
    lines = out.splitlines()
    check("session_start: reads the log the checker's way (fence blanked), body then version",
          lines[0] == "## 2026-01-01 \u2014 start" and lines[1].startswith("Last entry: 2026-01-01 (")
          and lines[2:4] == ["Decisions: none", "Docs: none"] and "left off here" in out
          and "fenced" not in out and re.fullmatch(r"repo-clean \d+\.\d+\.\d+", lines[-1]), out)
    check("session_start: no git output (D-027(a))", "git" not in out.lower(), out)
    check("session_start: prints the last entry's heading, so an old State shows its date",
          lines[0] == "## 2026-01-01 \u2014 start", out)
    check("session_start: prints the entry's age in days",
          "2026-01-01" in out and "days ago" in out, out)

    waiting = make_home(base, "waiting home")
    (waiting / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n| ID | Question | Revisit |\n|---|---|---|\n| D-002 | wait | later |\n\n"
        "## Fields\n\n## D-001 — a\nStatus: active\n\n## D-002 — wait\nStatus: open\nRevisit: later\n",
        encoding="utf-8")
    (waiting / "docs" / "DEFECTS.md").write_text("# Known defects\n\n## Open\n\n### DEF-01 — broken\n",
                                                 encoding="utf-8")
    _, out, _ = run_hook("session_start.py", {"session_id": "w1", "cwd": str(waiting),
                                              "source": "startup"}, base / "state_waiting")
    check("session_start: prints an Open: line per open decision and defect",
          "Open: D-002 — wait" in out and "Open: DEF-01 — broken" in out
          and "Open: D-001" not in out, out)

    unset_repo = base / "réviser projet sans config"
    unset_repo.mkdir()
    ns = base / "state_ss_nosetup"
    _, out1, _ = run_hook("session_start.py", {"session_id": "b1", "cwd": str(unset_repo)}, ns)
    _, out2, _ = run_hook("session_start.py", {"session_id": "b2", "cwd": str(unset_repo)}, ns)
    check("session_start: setup offer fires once", "init" in out1, out1)
    check("session_start: setup offer silent second time", out2.strip() == "", out2)

    blocked = base / "state is a file"
    blocked.write_text("x", encoding="utf-8")
    rc, out, err = run_hook("session_start.py", {"session_id": "b3", "cwd": str(unset_repo)},
                            blocked / "sub")
    check("session_start: an unwritable state dir still offers setup and exits 0",
          rc == 0 and "init" in out and not err, (rc, out, err))


def test_find_home(base):
    """D-023: the marker and the walk-up; the no-home glob; no pre-marker layout."""
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
    rc, out, _ = run_hook("session_start.py", {"session_id": "sr1", "cwd": str(root),
                                               "source": "startup"}, state)
    check("session_start: above homes, one line with three names and N more",
          "proj-a" in out and "and 1 more" in out and out.count("\n") == 1, out)


def test_launcher(base):
    """run.sh finds a Python, or says on stdout there is none, and exits 0 either way."""
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
    out = run("session_start", dict(os.environ, REPO_CLEAN_HOME=str(base / "state_launcher")),
              json.dumps({"cwd": str(empty)}))
    check("run.sh: with Python, it runs the hook", out.returncode == 0 and not out.stderr, out)


def test_bad_input(base):
    state = base / "state_bad"
    for text in ("", "not json{{{", json.dumps({"foo": "bar"}), "[1, 2]"):
        rc, out, err = run_hook("session_start.py", None, state, input_text=text)
        check(f"session_start.py: bad stdin {text[:8]!r} exits 0", rc == 0, (out, err))


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
        "Status: active extra words   Superseded-by: D-002\n\n"
        "## D-002 \u2014 b\n"
        "Status: superseded\n\n"
        # D-026: the legacy field is one aggregated finding, naming every entry that still has it.
        "## D-003 \u2014 c\n"
        "Status: open   Verdict: unresolved\n\n"
        "## D-780 \u2014 legacy field after a single space\n"
        "Status: active Verdict: rejected\n\n"
        # D-026: rejected needs no Superseded-by; superseded still does.
        "## D-781 \u2014 rejected, no link needed\n"
        "Status: rejected\n\n"
        "## D-782 \u2014 superseded, names no replacement\n"
        "Status: superseded\n\n"
        # a wrong-level heading is flagged, not silently skipped
        "### D-783 \u2014 wrong heading level\n"
        "Decision: x\n\n"
        # DEF-09 fire case: a title containing "Revisit" must not satisfy the real
        # Revisit: field requirement - the body has none, so this must still fire.
        "## D-778 \u2014 Revisit later\n"
        "Status: open\n\n"
        # DEF-08 quiet case: prose mentions Superseded-by: with a single space, and a
        # dangling-looking id, but must not be parsed as a real field.
        "## D-777 \u2014 prose mentions a field name\n"
        "Status: active\n"
        "Why: We considered Superseded-by: D-889 but rejected the idea.\n\n"
        # DEF-07 fire case: one decision superseding two, both directions must match.
        "## D-010 \u2014 consolidates two\n"
        "Status: active   Supersedes: D-011, D-012\n\n"
        "## D-011 \u2014 folded in, symmetric\n"
        "Status: superseded   Superseded-by: D-010\n\n"
        "## D-012 \u2014 folded in, NOT symmetric (missing Superseded-by)\n"
        "Status: superseded\n",
        encoding="utf-8",
    )
    (tmp / "CLAUDE.md").write_text(
        "| Doc | Path |\n"
        "|---|---|\n"
        "| routed doc | `./docs/ROUTED.md` |\n"
        "| checker | `scripts/tools/check_docs.py --root .` |\n\n"
        "See `docs/DOES_NOT_EXIST.md` and `C:\\Users\\x\\.claude\\plans\\p.md`.\n"
        "and a unix one `/home/me/notes.md`, and a Git Bash one `/c/Users/me/notes.md`.\n"
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
    (tmp / "README.md").write_text("fine. Shared drive D:\\data\\lake\\x.csv is fine (D-027(4)).\n", encoding="utf-8")
    (tmp / "docs" / "ROUTED.md").write_text("routed via the table with a leading ./\n", encoding="utf-8")
    (tmp / "docs" / "MOJIBAKE.md").write_bytes(b"# t\n\xff\xfe not utf-8\n")
    (tmp / "docs" / "ORPHAN.md").write_text("unrouted doc\n", encoding="utf-8")
    (tmp / "docs" / "FENCED.md").write_text(
        "# fenced\n"
        "Real content.\n"
        "```markdown\n"
        "## D-999 \u2014 a fake decision heading inside a fence\n"
        "Status: nonsense\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp / "docs" / "UNCLOSED.md").write_text(
        "# unclosed\n"
        "Real content.\n"
        "```markdown\n"
        "## D-998 \u2014 a fake heading in a fence nobody closed\n"
        "Status: nonsense\n",
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
        "body text with an outside path C:\\Users\\x\\plan.md\n\n"
        "### 2098-02-02 old-style heading after the first '##' heading\n\n"
        "## 2098-01-01 \u2014 duplicate date and no N\n"
        "Docs: none\n\n"
        "## 2098-01-03 bad grammar no dash\n"
        "Decisions: none\n\n"
        "## 2098-01-04 (1) \u2014 last entry\n"
        "Decisions: none\n"
        "Docs: none\n",
        encoding="utf-8",
    )

    found = []
    check_docs.run_generic_rules(check_docs.Ctx(tmp), found)

    def has(*substrings):
        return any(all(s in e for s in substrings) for e in found)

    def none_has(*substrings):
        return not any(all(s in e for s in substrings) for e in found)

    for label, ok in {
        "bad/missing Status shows the value": has("D-001", "bad/missing Status: 'active extra words'")
            and has("D-780", "bad/missing Status: 'active Verdict: rejected'"),
        "D-026: legacy Verdict is one aggregated finding naming its entries":
            len([e for e in found if "still carry Verdict:" in e]) == 1
            and has("2 entries still carry Verdict:", "D-003", "D-780"),
        "D-026: Status: rejected without Superseded-by is quiet": none_has("D-781"),
        "D-026: Status: superseded without Superseded-by fires": has("D-782", "names no Superseded-by"),
        "a ### decision heading is flagged": has("D-783", "decision heading must be '## D-NNN'"),
        "an unclosed fence is one finding, and nothing inside it fires":
            len([e for e in found if "unclosed code fence" in e]) == 1
            and has("UNCLOSED.md:3", "unclosed code fence") and none_has("D-998"),
        "Docs: field finding": has("Docs:"),
        "outside-repo path": has("absolute/outside-repo path in a living doc"),
        "missing path fires, suppressed one does not": has("does not exist") and none_has("SUPPRESSED_MISSING"),
        "missing Decisions:": has("missing a Decisions:"),
        "missing Docs:": has("missing a Docs:"),
        "log grammar": has("log heading grammar violated"),
        "duplicate log heading": has("duplicate log heading"),
        "### heading after ##": has("'###' dated heading appears after"),
        "open-questions table sync": has("missing from the Open questions table") or has("is not Status: open"),
        "open entry with no Revisit:": has("no Revisit:"),
        "unrouted doc": has("not referenced in"),
        "Decisions: references an unknown id": has("Decisions: references unknown"),
        "abs path in CLAUDE.md (unix, Git Bash, drive)": has("CLAUDE.md:", "absolute/outside-repo path"),
        "D-027(4): a non-home drive path is quiet": none_has("README.md:", "absolute/outside-repo path"),
        "D-027(4): a C:\\Users\\ path still fires": has("2098-08.md:", "absolute/outside-repo path"),
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
        "DEF-22: wrong case": has("docs/Archive/BANNER.md"),
        "DEF-22: a file with a trailing slash": has("docs/archive/BANNER.md/"),
        "DEF-22: right case and a real directory are quiet": not any(
            e.rstrip().endswith("docs/archive/BANNER.md") and "does not exist" in e for e in found)
            and not any(e.split()[-1] == "docs/archive/" for e in found),
    }.items():
        check(f"rules: {label}", ok, found if not ok else "")

    # D-027(6): an upgraded home's old State:/Next: lines and "Next Steps" headings are history,
    # not findings - on any entry, in any period file.
    h = base / "upgrade fixture"
    (h / "docs" / "log").mkdir(parents=True)
    (h / "docs" / "DECISIONS.md").write_text(
        "## Open questions\n\n## Fields\n\n## D-001 \u2014 a\nStatus: active\n",
        encoding="utf-8")
    (h / "CLAUDE.md").write_text("| Q | A |\n|---|---|\n| d | `docs/DECISIONS.md` |\n", encoding="utf-8")
    (h / "README.md").write_text("fine\n\n## Next Steps\n", encoding="utf-8")
    (h / "docs" / "log" / "2097-01.md").write_text(
        "## 2097-01-01 \u2014 first period\nDecisions: none\nDocs: none\nState: old\nNext: old\n",
        encoding="utf-8")
    (h / "docs" / "log" / "2097-02.md").write_text(
        "## 2097-02-01 \u2014 second period, first entry\nDecisions: none\nDocs: none\nState: x\n\n"
        "## Next Steps\n\n"
        "## 2097-02-02 \u2014 second period, last entry\nDecisions: none\nDocs: none\n",
        encoding="utf-8")
    ctx = check_docs.Ctx(h)
    f1 = []
    check_docs.run_generic_rules(ctx, f1)
    check("rules: D-027(6) old State:/Next: lines and a Next Steps heading are no finding", f1 == [], f1)

    o = base / "open items fixture"
    (o / "docs").mkdir(parents=True)
    check("rules: open_items with no register and no DEFECTS.md is empty", check_docs.open_items(o) == [])
    (o / "docs" / "DEFECTS.md").write_text("## Open\n\n### DEF-01 \u2014 broken\n", encoding="utf-8")
    check("rules: open_items reads DEFECTS.md with no register",
          check_docs.open_items(o) == ["DEF-01 \u2014 broken"], check_docs.open_items(o))
    (o / "docs" / "DECISIONS.md").write_text(
        "## D-001 \u2014 a\nStatus: active\n\n## D-002 \u2014 wait\nStatus: open\n", encoding="utf-8")
    (o / "docs" / "DEFECTS.md").unlink()
    check("rules: open_items reads open decisions with no DEFECTS.md",
          check_docs.open_items(o) == ["D-002 \u2014 wait"], check_docs.open_items(o))

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

    # a log with no recognisable dated entry is a finding, not a silent pass.
    z = make_home(base, "zero entry home")
    zlog = z / "docs" / "log" / "2026.md"
    for label, text, want in (
        ("a malformed dated heading is a grammar finding, not a crash",
         "## 2026-1-1 - typo date\n", "log heading grammar violated: ## 2026-1-1"),
        ("a log with no dated heading is a finding", "# 2026 log\n\nno entries yet\n", "no dated entry"),
        ("a home with no docs/log is a finding", None, "no dated entry"),
    ):
        if text is None:
            shutil.rmtree(z / "docs" / "log")
        else:
            zlog.write_text(text, encoding="utf-8")
        fz = []
        check_docs.run_generic_rules(check_docs.Ctx(z), fz)
        check(f"rules: {label}", any(want in e for e in fz), fz)


def main():
    with tempfile.TemporaryDirectory(prefix="repo_clean_selftest_") as tmp:
        base = Path(tmp)
        test_project_checker_never_run(base)
        test_failing_checker(base)
        test_session_start(base)
        test_find_home(base)
        test_plugin_core(base)
        test_launcher(base)
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
