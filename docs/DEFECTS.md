# Known defects

This file is authoritative for **what is broken and its status**.

Found 2026-09-18 by an adversarial pass against the checker: throwaway repos built to make
it crash, emit a wrong finding on valid input, or stay silent on input violating its own
documented rules. The bundled `--selfcheck` passed all 37 of its own assertions and caught
none of these — its fixtures were written by the same hand as the rules, so each proved its
rule *can* fire, and none proved a rule stays quiet when it should. The rebuilt selfcheck
(50 findings) now pairs every must-fire fixture with a must-not-fire one built from each
repro below.

`Status:` is `confirmed` (reproduced here), `reported` (found by the pass, not independently
reproduced), or `fixed` (with the commit that closed it). All 22 are now fixed; see
`git log --oneline -- skills/repo-clean/scripts/check_docs.py` for the closing commit.

## Fixed 2026-09-19

### DEF-01 — Crash on a repo path containing non-ASCII
Status: fixed
Was: `git_root()`'s `subprocess.run` had no `encoding=`, so git's UTF-8 output was decoded
with the console code page and the resulting path didn't exist — traceback, exit 1, and the
pre-commit hook (which calls with no `--root`) could never run for a user whose home
directory has an accent.
Fix: `encoding="utf-8"` on the subprocess call; git absent or failing now falls back to
`cwd` instead of being fatal (git is optional); `main()` catches any exception and exits 2.

### DEF-02 — Any backticked command with a flag is reported as a missing path
Status: fixed
Was: `PATH_LIKE` allowed spaces and swallowed a whole command line, so a backticked
`scripts/tools/check_docs.py --selfcheck` (the command this repo's own README tells users to
run) was reported as a missing path.
Fix: a backticked span with whitespace is split on whitespace and each token is tested
alone (`path_tokens_from_span`); `CANDIDATE_TOKEN_RE` requires a whitespace-free token.

### DEF-03 — The documented per-rule disable does not exist
Status: fixed
Was: no rule read a rule-id `CONFIG` key, so `CONFIG["<rule-id>"] = None` changed nothing.
Fix: `GENERIC_RULES` is `(rule_id, fn)` pairs; `run_generic_rules` skips any id mapped to
`None` in the merged config.

### DEF-04 — The installed hook is not executable in this repo
Status: fixed
Was: `scripts/hooks/pre-commit` was mode 100644 in the index while the skill's copy was
100755, so a Unix clone silently skipped the hook.
Fix: `git update-index --chmod=+x scripts/hooks/pre-commit`; `init.md` step 7 does the same
after copying, only when `.git` exists.

### DEF-05 — Only the first line of a `Docs:` field is read
Status: fixed
Was: the `Docs:`/`Decisions:` regex was single-line, so a wrapped field (this repo's own
convention) was never actually checked past its first line.
Fix: `parse_fields()` continues a field's value onto following non-blank lines that don't
themselves start a field.

### DEF-06 — `--root` loads the local extension from the wrong directory
Status: fixed
Was: the local extension was imported from the script's own directory rather than the
target repo's, so the installed copy and the plugin copy could reach different verdicts
against the same repo.
Fix: `local_module_dir(root)` — the script's own directory when the script is itself inside
`root`, otherwise `<root>/scripts/tools/`. `--init-config` writes there.

### DEF-07 — One decision superseding two is reported as asymmetric
Status: fixed
Was: only the first id in a `Supersedes:`/`Superseded-by:` list was captured.
Fix: both fields parse every id (`id_re.findall`); symmetry is checked per pair.

### DEF-08 — `Superseded-by:` written in prose is parsed as the field
Status: fixed
Was: fields were searched across the whole entry text, so a sentence mentioning the field
name was read as the field itself.
Fix: `parse_fields()` only starts a field at column 0 or after 2+ spaces on an
already-started field line; a single space before a colon-word is prose.

### DEF-09 — Two rules disagree about whether the heading is part of the entry
Status: fixed
Was: `decisions-integrity` read fields from the body only; `open-questions-sync` still
searched the whole entry including the heading.
Fix: every rule reads fields from `split_entries()`'s body only.

## Fixed 2026-09-19 (false positives)

### DEF-10 — Fenced code blocks are treated as document content
Status: fixed
Was: no rule was fence-aware, so an example inside a fenced block (a TODO comment, a
decision or log heading) tripped the rule that documents its own grammar.
Fix: `read_doc()` blanks fenced-block interiors (line numbers preserved); every rule reads
through it.

### DEF-11 — Non-path tokens in `Docs:` are resolved as paths
Status: fixed
Was: a parenthetical section number, a version string, a URL, or a Windows separator each
produced a "references missing" finding.
Fix: `docs_field_paths()` requires a slash-free token to end in `.md`; `none`, URLs, and
Windows drive paths are skipped silently.

### DEF-12 — The outside-repo-path regex misfires and misses
Status: fixed
Was: fired on a word followed by a colon and a backslash and on a drive-letter pattern
inside a regex example; missed Git Bash style absolute paths.
Fix: `outside_path_re` requires the drive letter not be preceded by a word/backslash
character and be followed by a word character; added `/<letter>/Users/`, `/<letter>/home/`.

### DEF-13 — Archive banner scanning is shallow and hits frozen prose
Status: fixed
Was: only the archive's top level was scanned, and any line containing a banner keyword —
even ordinary historical prose — was checked.
Fix: `rglob` finds nested archive dirs; only consecutive blockquote (`>`) lines are joined
and scanned.

### DEF-14 — Research fields take the first match anywhere in the file
Status: fixed
Was: prose above the header containing a field name won over the real header; nested
research subdirectories were skipped.
Fix: `parse_fields()` (column/spacing rule, not "anywhere") plus `rglob`.

### DEF-15 — Routing coverage counts any backtick in the routing file
Status: fixed
Was: a doc mentioned anywhere in the routing file passed, including outside the table, and
a leading `./` never matched.
Fix: only backticks on table rows (lines starting with `|`) count; `./` is normalized; the
finding text now says "not referenced in `<routing file>`'s table".

## Fixed 2026-09-19 (documentation contradicted code)

### DEF-16 — README claims a rule that does not exist
Status: fixed
Was: README stated the checker catches literal restatement of code constants; no such rule
exists.
Fix: README and `maintain.md` now say the checker verifies structure, not meaning, and
cannot compare docs to code or to each other.

### DEF-17 — README says maintain and reorganize install the checker
Status: fixed
Was: neither does; `maintain` only reports version drift and prints a copy command.
Fix: README now says only `init` installs, and only copies the pre-commit hook when `.git`
exists.

### DEF-18 — Documented log grammar is unenforced
Status: fixed
Was: a `State:` line on a non-last entry passed, and `(N)` numbering was never checked.
Fix: `diary-grammar` now enforces `(N)` numbering (first entry of a date unnumbered, then
`(2)`, `(3)`, ...) alongside `State:` on the last entry only. `example-layout.md` corrected
to match.

### DEF-19 — `--selfcheck` only works as the first argument
Status: fixed
Was: passed after another flag it was ignored; unknown flags were accepted silently.
Fix: CLI rebuilt on `argparse`; `--selfcheck` works anywhere in argv, unknown flags exit 2.

### DEF-20 — The config starter misstates how a version mismatch is reported
Status: fixed
Was: `LOCAL_STARTER` said a `CONFIG_VERSION` mismatch is a finding; the code reports it as
an internal error with a different exit code.
Fix: `LOCAL_STARTER` now says "internal error, exit 2".

### DEF-21 — `--root` pointed at a file crashes
Status: fixed
Was: only existence was checked, not that the target is a directory; traceback, exit 1.
Fix: `_resolve_root()` checks `is_dir()` and exits 2 with a message otherwise.

### DEF-22 — Directory paths and case differences are not checked
Status: fixed
Was: a backticked path ending in a separator was skipped, so a missing directory passed; a
case mismatch passed on a case-insensitive filesystem.
Fix: `exists_exact()` walks path segments through `os.listdir()` (case-sensitive on Windows
too); a trailing separator requires the final segment to be a real directory.
