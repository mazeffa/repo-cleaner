# Known defects

This file is authoritative for **what is broken and its status**.

Found 2026-09-18 by an adversarial pass against the checker: throwaway repos built to make
it crash, emit a wrong finding on valid input, or stay silent on input violating its own
documented rules. The bundled `--selfcheck` passes all 37 of its own assertions and caught
none of these — its fixtures are written by the same hand as the rules, so each one proves
its rule *can* fire, and nothing proves a rule stays quiet when it should.

`Status:` is `confirmed` (reproduced here), `reported` (found by the pass, not independently
reproduced), or `fixed` (with the commit that closed it).

## Open, blocks use

### DEF-01 — Crash on a repo path containing non-ASCII
Status: confirmed
Where: `skills/repo-clean/scripts/check_docs.py` git_root(), and the iterdir at line 106
Repro: init a repo under a directory named `resume` with accented characters, run the
checker with no `--root`. `subprocess.run(..., text=True)` has no `encoding=`, so git's
UTF-8 output is decoded with the console code page and the resulting path does not exist.
Traceback, exit 1 — not the documented exit 2. The pre-commit hook calls the checker with
no `--root`, so a user whose home directory has an accent can never commit.

### DEF-02 — Any backticked command with a flag is reported as a missing path
Status: confirmed
Where: `skills/repo-clean/scripts/check_docs.py` PATH_LIKE and candidate_path()
Repro: a routing file containing the command this repo's own README tells users to run,
backticked, with the file present. Output: `path does not exist: scripts/tools/check_docs.py
--selfcheck`, exit 1. `path_cmd_prefixes` strips the interpreter, then PATH_LIKE allows
spaces and hyphens and swallows the rest of the line. Same for two paths joined by "and".
This fails the gate on correct input, which is what teaches people to pass `--no-verify`.

### DEF-03 — The documented per-rule disable does not exist
Status: confirmed
Where: `skills/repo-clean/scripts/check_docs.py` module docstring, suppression layer 3
Repro: a local config setting a rule id to None changes nothing; the rule still fires. No
rule reads a rule-id CONFIG key. `paths-exist`, `date-stamped-filenames` and
`archive-banner-paths` have no gating key of any kind, so there is no way to turn off
DEF-02 short of editing the core.

### DEF-04 — The installed hook is not executable in this repo
Status: confirmed
Where: `scripts/hooks/pre-commit`, mode 100644 in the index
Repro: `git ls-files -s scripts/hooks/pre-commit`. The skill's copy is 100755; the copy
installed here is not. On a Unix clone git skips a non-executable hook silently, so this
repo's claim that the hook enforces the checker holds on Windows only.

## Open, silent failures

### DEF-05 — Only the first line of a `Docs:` field is read
Status: confirmed
Where: `skills/repo-clean/scripts/check_docs.py` check_log_fields_resolve()
Repro: a log entry whose `Docs:` wraps, with a nonexistent file on the second line. Exit 0.
The regex is single-line. This repo's own log wraps `Docs:` across three lines, so that
field has never been checked here.

### DEF-06 — `--root` loads the local extension from the wrong directory
Status: reported
Where: `skills/repo-clean/scripts/check_docs.py` load_local_module()
The extension is imported from the script's own directory rather than the target repo's, so
the installed copy and the plugin copy run with different config against the same repo and
reach different verdicts. `--init-config` run from the plugin path writes the starter into
the plugin cache instead of the repo.

## Open, false positives

### DEF-07 — One decision superseding two is reported as asymmetric
Status: reported
Only the first id in a `Supersedes:` list is captured. Consolidating two decisions into one
— the normal case that `reorganize` produces — fails the check.

### DEF-08 — `Superseded-by:` written in prose is parsed as the field
Status: reported
The fields are searched across the whole entry, so an explanatory line mentioning the field
name is read as the field itself.

### DEF-09 — Two rules disagree about whether the heading is part of the entry
Status: reported
`decisions-integrity` reads fields from the body only; `open-questions-sync` still searches
the heading. A decision whose title contains a field name can hide an open entry, and a
title containing `Revisit` satisfies the revisit requirement. This repo's D-005 has a title
of exactly that shape.

### DEF-10 — Fenced code blocks are treated as document content
Status: reported
No rule is fence-aware. A TODO comment in a python example fires banned-headers; an example
decision heading fires decisions-integrity; an example log heading fires diary-grammar. Any
doc that documents this system's own grammar will trip it.

### DEF-11 — Non-path tokens in `Docs:` are resolved as paths
Status: reported
A parenthetical section number, a version string, a URL, or a Windows-style separator each
produce a "references missing" finding. A URL additionally becomes a network path lookup on
Windows.

### DEF-12 — The outside-repo-path regex misfires and misses
Status: reported
Fires on a word followed by a colon and a backslash, and on a drive-letter pattern inside a
regex example. Misses Git Bash style absolute paths, which is the shell this project is
developed in.

### DEF-13 — Archive banner scanning is shallow and hits frozen prose
Status: reported
Only the top level of the archive is scanned and only lines containing a banner keyword, so
a wrapped banner or a nested archive directory is skipped — while a historical body line
that happens to contain a banner keyword is checked, though archives are exempt from every
other rule.

### DEF-14 — Research fields take the first match anywhere in the file
Status: reported
Prose above the header containing the field name wins over the real header. Research docs in
a nested subdirectory are skipped entirely.

### DEF-15 — Routing coverage counts any backtick in the routing file
Status: reported
A doc mentioned anywhere in the routing file passes, including outside the table, while the
finding text claims the table was checked. A path written with a leading dot-slash in the
table does not match.

## Open, documentation contradicts code

### DEF-16 — README claims a rule that does not exist
Status: confirmed
The README states the checker catches literal restatement of code constants. No rule
compares documents to code; the word does not appear in the checker.

### DEF-17 — README says maintain and reorganize install the checker
Status: reported
Neither does. `maintain` reports version drift and prints a copy command; `reorganize` never
mentions installing.

### DEF-18 — Documented log grammar is unenforced
Status: reported
A `State:` line on a non-last entry passes, and the `(N)` numbering rule is not checked.
`example-layout.md` and this repo's own log also disagree on whether the first entry sharing
a date is numbered.

### DEF-19 — `--selfcheck` only works as the first argument
Status: reported
Passed after another flag it is ignored and a normal check runs. Unknown flags are accepted
silently rather than rejected.

### DEF-20 — The config starter misstates how a version mismatch is reported
Status: reported
It says a CONFIG_VERSION mismatch is a finding; the code reports it as an internal error
with a different exit code.

### DEF-21 — `--root` pointed at a file crashes
Status: reported
Only existence is checked, not that the target is a directory. Traceback and exit 1, where
exit 2 is documented for a bad `--root`.

### DEF-22 — Directory paths and case differences are not checked
Status: reported
A backticked path ending in a separator is skipped, so a missing directory passes. On a
case-insensitive filesystem a path whose case does not match passes locally and would fail
on Linux.
